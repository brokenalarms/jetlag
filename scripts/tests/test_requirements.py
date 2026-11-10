"""
Runtime vs dev dependency split — the app bundle vendors scripts/requirements.txt
verbatim into Contents/Resources/scripts/site-packages (see the `Bundle scripts`
build phase in macos/project.yml), so anything listed there ships to every user.
Dev-only tooling (pytest and its plugins, pyrefly, ruff) belongs in
scripts/requirements-dev.txt instead, which the bundle build deletes.
"""

from pathlib import Path

from helpers import SCRIPT_DIR

DEV_PACKAGES = {"pytest", "pytest-xdist", "pyrefly", "ruff"}


def _package_names(requirements_path: Path) -> set[str]:
    lines = [
        line.strip()
        for line in requirements_path.read_text().splitlines()
        if line.strip()
    ]
    return {line.split("==")[0].split(">=")[0].strip() for line in lines}


def test_runtime_requirements_excludes_dev_tooling():
    packages = _package_names(SCRIPT_DIR / "requirements.txt")
    assert packages == {"humanize", "PyYAML"}
    assert packages.isdisjoint(DEV_PACKAGES)


def test_dev_requirements_holds_test_and_lint_tooling():
    packages = _package_names(SCRIPT_DIR / "requirements-dev.txt")
    assert packages == DEV_PACKAGES
