"""
Pytest configuration — enforce required external tools are installed.

Tests must never be skipped because a tool is missing. If a tool is required,
install it automatically. macOS-only tests (tag/SetFile) are skipped on Linux.
"""

from __future__ import annotations

import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.metadata import metadata_service as exiftool

_template_video: Path | None = None


def _ensure_template() -> Path:
    global _template_video
    if _template_video is None:
        d = tempfile.mkdtemp(prefix="pytest_video_template_")
        _template_video = Path(d) / "template.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=0.04",
            "-c:v", "libx264", "-t", "0.04", "-pix_fmt", "yuv420p",
            str(_template_video)
        ], capture_output=True, check=True)
        atexit.register(lambda: shutil.rmtree(d, ignore_errors=True))
    return _template_video


def create_test_video(path, **exif_tags):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_ensure_template(), str(path))
    if exif_tags:
        tag_args = [f"-{field}={value}" for field, value in exif_tags.items()]
        exiftool.write_tags(str(path), tag_args)


_template_photo: Path | None = None


def _ensure_template_photo() -> Path:
    """A real JPEG. The MP4 template has no ExifIFD group, so binary-EXIF stills
    tags such as OffsetTimeOriginal cannot round-trip through it at all."""
    global _template_photo
    if _template_photo is None:
        d = tempfile.mkdtemp(prefix="pytest_photo_template_")
        _template_photo = Path(d) / "template.jpg"
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x48:d=0.04",
            "-frames:v", "1", str(_template_photo)
        ], capture_output=True, check=True)
        atexit.register(lambda: shutil.rmtree(d, ignore_errors=True))
    return _template_photo


def create_test_photo(path, **exif_tags):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_ensure_template_photo(), str(path))
    if exif_tags:
        tag_args = [f"-{field}={value}" for field, value in exif_tags.items()]
        exiftool.write_tags(str(path), tag_args)


# Map of required tool -> install commands by platform.
# exiftool is vendored at scripts/tools/ — no install needed.
REQUIRED_TOOLS = {
    "ffmpeg": {
        "linux": ["apt-get", "install", "-y", "-qq", "ffmpeg"],
        "darwin": ["brew", "install", "ffmpeg"],
    },
}

# Python packages required at import time by the scripts under test.
REQUIRED_PYTHON_PACKAGES = {
    "humanize": "humanize",
    "yaml": "pyyaml",
}

# macOS-only tools — required on macOS, skipped on Linux
MACOS_TOOLS = ["tag", "SetFile"]


def _install_tool(name, install_cmd):
    """Install a missing tool, raising UsageError on failure."""
    platform = "darwin" if sys.platform == "darwin" else "linux"
    print(f"Installing {name}...")
    result = subprocess.run(install_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise pytest.UsageError(
            f"Failed to install {name}: {result.stderr}\n"
            f"Install manually — see scripts/tests/README.md"
        )
    # Verify it's now on PATH
    if not shutil.which(name):
        raise pytest.UsageError(
            f"Installed {name} but it's still not on PATH.\n"
            f"Install manually — see scripts/tests/README.md"
        )


def _install_python_package(import_name, pip_name):
    """Install a missing Python package into the running interpreter's environment."""
    print(f"Installing Python package {pip_name}...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", pip_name],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise pytest.UsageError(
            f"Failed to install {pip_name}: {result.stderr}\n"
            f"Install manually: pip install {pip_name}"
        )


def pytest_addoption(parser):
    """Register custom CLI flags."""
    parser.addoption(
        "--perf-baseline-scripts-dir", default=None,
        help="Path to a checkout of the scripts/ dir to compare against (e.g. origin/main)",
    )
    parser.addoption(
        "--perf-results-file", default=None,
        help="Path to write perf results JSON for CI summaries",
    )


def pytest_configure(config):
    """Install missing tools and packages before tests run."""
    platform = "darwin" if sys.platform == "darwin" else "linux"

    for tool, commands in REQUIRED_TOOLS.items():
        if not shutil.which(tool):
            if platform in commands:
                _install_tool(tool, commands[platform])
            else:
                raise pytest.UsageError(
                    f"Required tool {tool} not installed and no install command for {platform}.\n"
                    f"Install manually — see scripts/tests/README.md"
                )

    for import_name, pip_name in REQUIRED_PYTHON_PACKAGES.items():
        try:
            __import__(import_name)
        except ImportError:
            _install_python_package(import_name, pip_name)

    if sys.platform == "darwin":
        # tag is vendored at scripts/tools/tag; SetFile is from Xcode
        missing_mac = [t for t in MACOS_TOOLS if not shutil.which(t)]
        # Don't fail for 'tag' — it's resolved via lib/tools.py from scripts/tools/
        missing_mac = [t for t in missing_mac if t != "tag"]
        if missing_mac:
            raise pytest.UsageError(
                f"Required macOS tools not installed: {', '.join(missing_mac)}\n"
                f"SetFile: xcode-select --install"
            )

    config._perf_results = []
    config._quiet_mode = not os.environ.get("CI")
    if config._quiet_mode:
        config.option.verbose = -1


@pytest.hookimpl(trylast=True)
def pytest_sessionstart(session):
    if not getattr(session.config, "_quiet_mode", False):
        return
    terminal = session.config.pluginmanager.get_plugin("terminalreporter")
    if terminal:
        terminal._tw.line("running tests...")

        def _quiet_summary_stats():
            s = getattr(terminal, "_session", None)
            if s and s.exitstatus == 0:
                passed = len(terminal.stats.get("passed", []))
                terminal._tw.line(f"all {passed} tests passed")

        terminal.summary_stats = _quiet_summary_stats


def pytest_report_teststatus(report, config):
    if not getattr(config, "_quiet_mode", False):
        return None
    if report.when == "call":
        if report.passed:
            return "passed", "", ""
        if report.failed:
            return "failed", "", "FAILED"
        if report.skipped:
            return "skipped", "", ""
    if report.when in ("setup", "teardown"):
        if report.failed:
            return "error", "", "ERROR"
        if report.skipped:
            return "skipped", "", ""
        return "", "", ""


def pytest_sessionfinish(session, exitstatus):
    results_path = session.config.getoption("--perf-results-file", default=None)
    results = getattr(session.config, "_perf_results", [])
    if results_path and results:
        path = Path(results_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(results, indent=2) + "\n")


