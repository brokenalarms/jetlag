"""
Pytest configuration — enforce required external tools are installed.

Tests must never be skipped because a tool is missing. If a tool is required,
install it automatically. macOS-only tests (tag/SetFile) are skipped on Linux.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# Map of required tool -> install commands by platform.
# Each entry is {tool_name: {platform: [install_command]}}.
REQUIRED_TOOLS = {
    "ffmpeg": {
        "linux": ["apt-get", "install", "-y", "-qq", "ffmpeg"],
        "darwin": ["brew", "install", "ffmpeg"],
    },
    "exiftool": {
        "linux": ["apt-get", "install", "-y", "-qq", "libimage-exiftool-perl"],
        "darwin": ["brew", "install", "exiftool"],
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
        "--perf-baseline", action="store_true", default=False,
        help="Record performance baselines instead of comparing against them",
    )
    parser.addoption(
        "--perf-baseline-file", default=None,
        help="Path to baseline JSON file (default: tests/perf_baseline.json)",
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
        missing_mac = [t for t in MACOS_TOOLS if not shutil.which(t)]
        if missing_mac:
            raise pytest.UsageError(
                f"Required macOS tools not installed: {', '.join(missing_mac)}\n"
                f"tag: brew install tag\n"
                f"SetFile: xcode-select --install"
            )

    config._perf_results = []


@pytest.hookimpl(trylast=True)
def pytest_sessionstart(session):
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


