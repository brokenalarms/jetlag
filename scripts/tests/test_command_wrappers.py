"""
The commands a user runs: one <command>.sh at the top of scripts/ per entry point
in cli/, each launched through lib/launch.sh.

A user (and the app) only ever runs the .sh files, so these guard the pairing —
a cli/ module without a wrapper is a command nobody can run the documented way —
and that a wrapper resolves its own paths when started from another directory,
which is how a user in their footage folder runs it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).parent.parent
ENTRY_POINTS = sorted(
    p.stem for p in (SCRIPT_DIR / "cli").glob("*.py")
    if p.stem not in ("__init__", "results")
)
WRAPPERS = sorted(p.stem for p in SCRIPT_DIR.glob("*.sh"))


def test_every_entry_point_has_a_wrapper_and_every_wrapper_an_entry_point():
    assert [name.replace("_", "-") for name in ENTRY_POINTS] == WRAPPERS


@pytest.mark.parametrize("command", WRAPPERS)
def test_wrapper_runs_from_another_directory(command, tmp_path):
    """--help from an unrelated cwd: the wrapper finds lib/, cli/ and the
    interpreter from its own location, and usage names the command run."""
    completed = subprocess.run(
        [str(SCRIPT_DIR / f"{command}.sh"), "--help"],
        cwd=tmp_path, capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.startswith(f"usage: {command}.sh ")
