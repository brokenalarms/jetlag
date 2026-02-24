"""
Pytest configuration — enforce required external tools are installed.

Tests must never be skipped because a tool is missing. If a tool is required,
install it automatically. macOS-only tests (tag/SetFile) are skipped on Linux.
"""

import shutil
import subprocess
import sys

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


def pytest_collection_modifyitems(config, items):
    """Skip macOS-only tests when running on Linux."""
    if sys.platform == "darwin":
        return

    skip_marker = pytest.mark.skip(reason="requires macOS — Finder tags and birth time don't exist on Linux")
    for item in items:
        source = _get_test_source(item)
        if source and _uses_macos_tools(source):
            item.add_marker(skip_marker)


def _get_test_source(item):
    """Get the source code of a test function and its class."""
    import inspect
    try:
        source = inspect.getsource(item.obj)
        if item.cls:
            source += inspect.getsource(item.cls)
        return source
    except (TypeError, OSError):
        return None


def _uses_macos_tools(source: str) -> bool:
    """Check if source code references macOS-only tools."""
    return '"tag"' in source or '"SetFile"' in source or "'tag'" in source or "'SetFile'" in source
