#!/usr/bin/env python3
"""
Tests for probe-camera.py, which tells the app what camera shot a folder's media.

The app fills a profile's Make/Model from it and picks the profile matching an
inserted card, so each extension has to report the camera its files carry —
separately, since a card holds a camera's stills and videos under different
profiles — and nothing it was not told by the files.
"""

import json
import subprocess
import sys
from pathlib import Path

from conftest import create_test_photo, create_test_video

SCRIPT_DIR = Path(__file__).parent.parent


def probe(*args) -> list[dict]:
    result = subprocess.run([sys.executable, str(SCRIPT_DIR / "probe-camera.py"), *map(str, args)],
                            capture_output=True, text=True, cwd=SCRIPT_DIR)
    assert result.returncode == 0, result.stderr
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def test_each_extension_reports_the_camera_its_files_carry(tmp_path):
    """A card with stills and video from one camera reports both, per extension."""
    create_test_photo(tmp_path / "DCIM" / "100MSDCF" / "A7V0001.JPG", Make="SONY", Model="ILCE-7M5")
    create_test_photo(tmp_path / "DCIM" / "101MSDCF" / "A7V0002.JPG", Make="SONY", Model="ILCE-7M5")
    create_test_video(tmp_path / "PRIVATE" / "C0001.MP4", Make="SONY", Model="ILCE-7M5")

    found = probe(tmp_path)

    assert found == [
        {"extension": ".jpg", "type": "photo", "folder": str(tmp_path / "DCIM"),
         "files": 2, "make": "SONY", "model": "ILCE-7M5"},
        {"extension": ".mp4", "type": "video", "folder": str(tmp_path / "PRIVATE"),
         "files": 1, "make": "SONY", "model": "ILCE-7M5"},
    ], f"Actual: {found}, Expected: one SONY ILCE-7M5 entry per extension, with its folder"


def test_files_without_a_camera_report_none(tmp_path):
    """A camera that records no Make/Model is reported as such, not guessed."""
    create_test_video(tmp_path / "clip.mp4")

    found = probe(tmp_path)

    assert found == [{"extension": ".mp4", "type": "video", "folder": str(tmp_path), "files": 1}], \
        f"Actual: {found}, Expected: an entry with no make or model"


def test_a_single_file_can_be_probed(tmp_path):
    """The profile editor can read the camera from one sample file."""
    sample = tmp_path / "A7V0001.JPG"
    create_test_photo(sample, Make="SONY", Model="ILCE-7M5")

    found = probe(sample)

    assert found == [{"extension": ".jpg", "type": "photo", "folder": str(tmp_path),
                      "files": 1, "make": "SONY", "model": "ILCE-7M5"}]
