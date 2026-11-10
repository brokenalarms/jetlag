"""
Pytest configuration — enforce required external tools are installed.

Tests must never be skipped because a tool is missing. If a tool is required,
install it automatically. macOS-only tests (tag/SetFile) are skipped on Linux.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

from helpers import SCRIPT_DIR
from helpers.processes import leaked_metadata_pids
from lib.exiftool import exiftool


@pytest.fixture(scope="session", autouse=True)
def _close_exiftool_at_session_end():
    """The module-level exiftool is otherwise only closed via atexit, which does
    not run when an xdist worker is torn down non-gracefully — its -stay_open
    child then outlives the suite."""
    yield
    exiftool.close()


@pytest.fixture(autouse=True)
def _fresh_metadata_cache():
    """Every test starts with no cached metadata, so a file another test wrote
    (or a path a temp dir reused) is never answered from a stale read."""
    exiftool.cache.clear()
    yield
    exiftool.cache.clear()


@pytest.fixture
def metadata_client():
    """Registers an ExifTool client constructed by a test for guaranteed close()
    via the context-manager protocol, even if the test body raises."""
    with contextlib.ExitStack() as stack:
        yield stack.enter_context


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace with source and target directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        source = workspace / "source"
        target = workspace / "target"
        source.mkdir()
        target.mkdir()
        yield {"root": workspace, "source": source, "target": target}


@pytest.fixture
def test_profile(temp_workspace, monkeypatch):
    """Create a test profile in an isolated copy of media-profiles.yaml.

    The copy plus the JETLAG_PROFILES_FILE override keeps every test (and its
    spawned scripts) off the shared repo file, which is what allows the suite
    to run in parallel workers. Tests that need to tweak the profile edit the
    copy via os.environ["JETLAG_PROFILES_FILE"].
    """
    profiles_path = temp_workspace["root"] / "media-profiles.yaml"

    with open(SCRIPT_DIR / "media-profiles.yaml") as f:
        profiles = yaml.safe_load(f)

    profiles["profiles"]["_test"] = {
        "source_dir": str(temp_workspace["source"]),
        "ready_dir": str(temp_workspace["target"]),
        "file_extensions": [".mp4"],
        "tags": ["test-camera"],
        "exif": {"make": "Test", "model": "Camera"},
        "companion_extensions": [".thm", ".lrv"],
    }

    with open(profiles_path, "w") as f:
        yaml.dump(profiles, f, default_flow_style=False, sort_keys=False)

    monkeypatch.setenv("JETLAG_PROFILES_FILE", str(profiles_path))
    yield "_test"


class FakeMetadata:
    """Stands in for exiftool behind the shared metadata client.

    files maps a path to the tags a read returns for it, keyed as exiftool's
    short output names them (DateTimeOriginal, MediaCreateDate, …); a file it
    does not know reads as having no tags. Every write is recorded in writes as
    (path, tag_args) and reported as made.
    """

    def __init__(self):
        self.files: dict[str, dict[str, str]] = {}
        self.writes: list[tuple[str, list[str]]] = []

    def read_tags(self, file_path, tags, extra_args=None):
        return dict(self.files.get(str(file_path), {}))

    def write_tags(self, file_path, tag_args):
        self.writes.append((str(file_path), list(tag_args)))
        exiftool.cache.pop(str(file_path), None)
        return True

    def execute(self, *args):
        raise AssertionError(f"exiftool run with a fake metadata client: {args}")


@pytest.fixture
def fake_metadata(monkeypatch):
    """Route the metadata client's reads and writes to a FakeMetadata, so a test
    runs the real lib code with no exiftool process behind it."""
    fake = FakeMetadata()
    monkeypatch.setattr(exiftool, "read_tags", fake.read_tags)
    monkeypatch.setattr(exiftool, "write_tags", fake.write_tags)
    monkeypatch.setattr(exiftool, "execute", fake.execute)
    return fake


# Map of required tool -> install commands by platform.
# exiftool is vendored at scripts/tools/ — no install needed.
REQUIRED_TOOLS = {
    "ffmpeg": {
        "linux": ["apt-get", "install", "-y", "-qq", "ffmpeg"],
        "darwin": ["brew", "install", "ffmpeg"],
    },
}

# Python packages required at import time by the scripts under test, by import
# name. They come from scripts/requirements.txt via `make test-scripts`; the
# suite never installs into whichever interpreter happens to run it.
REQUIRED_PYTHON_PACKAGES = ["humanize", "yaml"]

# macOS-only tools — required on macOS, skipped on Linux
MACOS_TOOLS = ["tag", "SetFile"]


def _install_tool(name, install_cmd):
    """Install a missing tool, raising UsageError on failure."""
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


def pytest_configure(config):
    """Install missing tools and check Python packages before tests run."""
    platform = "darwin" if sys.platform == "darwin" else "linux"

    # Tests run cli/<command>.py directly; lib/launch.sh gives a command scripts/
    # on PYTHONPATH, so give every subprocess the same.
    pythonpath = os.environ.get("PYTHONPATH")
    os.environ["PYTHONPATH"] = str(SCRIPT_DIR) + (os.pathsep + pythonpath if pythonpath else "")

    for tool, commands in REQUIRED_TOOLS.items():
        if not shutil.which(tool):
            if platform in commands:
                _install_tool(tool, commands[platform])
            else:
                raise pytest.UsageError(
                    f"Required tool {tool} not installed and no install command for {platform}.\n"
                    f"Install manually — see scripts/tests/README.md"
                )

    missing_packages = []
    for import_name in REQUIRED_PYTHON_PACKAGES:
        try:
            __import__(import_name)
        except ImportError:
            missing_packages.append(import_name)
    if missing_packages:
        raise pytest.UsageError(
            f"Python packages missing from {sys.executable}: {', '.join(missing_packages)}\n"
            "Run the suite with `make test-scripts`, which builds scripts/.venv from "
            "scripts/requirements.txt and scripts/requirements-dev.txt."
        )

    if sys.platform == "darwin":
        # tag is vendored at scripts/tools/tag; SetFile is from Xcode
        missing_mac = [t for t in MACOS_TOOLS if not shutil.which(t)]
        # Don't fail for 'tag' — it is vendored in scripts/tools/
        missing_mac = [t for t in missing_mac if t != "tag"]
        if missing_mac:
            raise pytest.UsageError(
                f"Required macOS tools not installed: {', '.join(missing_mac)}\n"
                f"SetFile: xcode-select --install"
            )

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
    leaked = leaked_metadata_pids()
    if leaked:
        message = "leaked metadata subprocess(es) survived the test session: " + ", ".join(leaked)
        terminal = session.config.pluginmanager.get_plugin("terminalreporter")
        if terminal:
            terminal.write_line(message, red=True, bold=True)
        else:
            print(message, file=sys.stderr)
        session.exitstatus = 1


