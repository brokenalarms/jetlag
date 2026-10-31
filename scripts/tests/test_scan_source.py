#!/usr/bin/env python3
"""
Tests for scan-source.py, which tells the app how much media a source holds and
whether its filenames carry dates, so the app keeps no copy of that logic.
"""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.parent


def scan(path, *args) -> dict:
    result = subprocess.run([sys.executable, str(SCRIPT_DIR / "scan-source.py"), str(path), *args],
                            capture_output=True, text=True, cwd=SCRIPT_DIR)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def test_count_includes_any_case_extension(tmp_path):
    """A card with .MP4 and .mp4 clips reports every one in the Run count."""
    touch(tmp_path / "a.MP4")
    touch(tmp_path / "sub" / "b.mp4")
    touch(tmp_path / "notes.txt")

    found = scan(tmp_path, "--extensions", ".mp4", "--count")

    assert found == {"media_files": 2}, f"Actual: {found}, Expected: 2 media files"


def test_count_excludes_hidden_files(tmp_path):
    """exFAT ._ companions are not clips and must not inflate the count."""
    touch(tmp_path / "a.mp4")
    touch(tmp_path / "._a.mp4")

    found = scan(tmp_path, "--extensions", ".mp4", "--count")

    assert found == {"media_files": 1}, f"Actual: {found}, Expected: hidden file excluded"


def test_dated_filename_is_reported(tmp_path):
    """A source whose clips are named with a date lets the app offer filename timestamps."""
    touch(tmp_path / "plain.mp4")
    touch(tmp_path / "VID_20240315_101500.mp4")

    found = scan(tmp_path, "--extensions", ".mp4", "--timestamped-names")

    assert found == {"has_timestamped_names": True}, f"Actual: {found}, Expected: True"


def test_undated_filenames_are_reported(tmp_path):
    """A source with no dated names reports false."""
    touch(tmp_path / "plain.mp4")
    touch(tmp_path / "C0001.mp4")

    found = scan(tmp_path, "--extensions", ".mp4", "--timestamped-names")

    assert found == {"has_timestamped_names": False}, f"Actual: {found}, Expected: False"


def test_missing_path_exits_with_error(tmp_path):
    """A source that was removed fails loudly rather than reporting zero."""
    result = subprocess.run([sys.executable, str(SCRIPT_DIR / "scan-source.py"), str(tmp_path / "gone"),
                             "--extensions", ".mp4", "--count"],
                            capture_output=True, text=True, cwd=SCRIPT_DIR)
    assert result.returncode == 1 and "does not exist" in result.stderr
