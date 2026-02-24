#!/usr/bin/env python3
"""
Tests for ExifToolStayOpen — verifies the stay_open protocol correctly
passes commands to exiftool and returns accurate results.
"""

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))
from lib.exiftool import ExifToolStayOpen


@pytest.fixture
def test_mp4(tmp_path):
    """Create a minimal mp4 with known EXIF metadata."""
    path = tmp_path / "test.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=16x16:d=0.04",
        "-c:v", "libx264", "-t", "0.04", str(path)
    ], capture_output=True, check=True)
    subprocess.run([
        "exiftool", "-overwrite_original",
        "-DateTimeOriginal=2025:10:05 10:00:00+09:00",
        "-Make=TestMake", "-Model=TestModel",
        str(path)
    ], capture_output=True, check=True)
    return path


class TestExifToolStayOpen:
    """Functional tests for the stay_open protocol wrapper."""

    def test_read_tags_matches_subprocess(self, test_mp4):
        """read_tags returns the same field values as a subprocess exiftool call."""
        fields = ["DateTimeOriginal", "Make", "Model"]

        # Read via subprocess
        result = subprocess.run(
            ["exiftool", "-s"] + [f"-{f}" for f in fields] + [str(test_mp4)],
            capture_output=True, text=True, check=True,
        )
        expected = {}
        for line in result.stdout.strip().split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                expected[key.strip()] = value.strip()

        # Read via stay_open
        with ExifToolStayOpen() as et:
            actual = et.read_tags(str(test_mp4), fields)

        assert actual == expected

    def test_write_tags_persists(self, test_mp4):
        """write_tags actually writes data that a subsequent subprocess read can see."""
        with ExifToolStayOpen() as et:
            et.write_tags(str(test_mp4), ["-Make=NewMake", "-Model=NewModel"])

        # Verify via subprocess
        result = subprocess.run(
            ["exiftool", "-s3", "-Make", "-Model", str(test_mp4)],
            capture_output=True, text=True, check=True,
        )
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "NewMake"
        assert lines[1] == "NewModel"

    def test_multiple_reads_same_session(self, test_mp4, tmp_path):
        """Multiple read_tags calls within one session all return correct data."""
        # Create a second file with different metadata
        mp4_b = tmp_path / "b.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=16x16:d=0.04",
            "-c:v", "libx264", "-t", "0.04", str(mp4_b)
        ], capture_output=True, check=True)
        subprocess.run([
            "exiftool", "-overwrite_original",
            "-DateTimeOriginal=2024:01:01 12:00:00+00:00",
            "-Make=OtherMake",
            str(mp4_b)
        ], capture_output=True, check=True)

        with ExifToolStayOpen() as et:
            data_a = et.read_tags(str(test_mp4), ["Make"])
            data_b = et.read_tags(str(mp4_b), ["Make"])

        assert data_a["Make"] == "TestMake"
        assert data_b["Make"] == "OtherMake"

    def test_read_after_write_sees_update(self, test_mp4):
        """A read_tags after write_tags within the same session sees the new value."""
        with ExifToolStayOpen() as et:
            et.write_tags(str(test_mp4), ["-Make=Updated"])
            data = et.read_tags(str(test_mp4), ["Make"])

        assert data["Make"] == "Updated"

    def test_context_manager_cleanup(self):
        """Exiting the context manager terminates the exiftool process."""
        with ExifToolStayOpen() as et:
            proc = et._proc
            assert proc.poll() is None  # still running

        assert proc.poll() is not None  # terminated after __exit__
