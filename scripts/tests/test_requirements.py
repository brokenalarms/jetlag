"""
Runtime vs dev dependency split — the app bundle vendors scripts/requirements.txt
verbatim into Contents/Resources/scripts/site-packages (see the `Bundle scripts`
build phase in macos/project.yml), so anything listed there ships to every user.
Dev-only tooling (pytest, pyrefly) belongs in scripts/requirements-dev.txt instead,
which nothing in the bundle build reads.
"""

from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.parent
DEV_PACKAGES = {"pytest", "pyrefly"}


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


def test_dev_requirements_holds_pytest_and_pyrefly():
    packages = _package_names(SCRIPT_DIR / "requirements-dev.txt")
    assert packages == DEV_PACKAGES
