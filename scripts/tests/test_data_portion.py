#!/usr/bin/env python3
"""
verify-card compares a photo jetlag has written with its card file by the photo's data
portion, because a metadata write changes the file's total size. For a JPEG that is
everything from the first start-of-scan marker to the end of the file.

The regression test runs the pipeline's own writers (tag-media, then
fix-media-timestamp) on a JPEG and requires its data portion to be what it was, while
the file around it has visibly changed. If a writer touched the image data, or the
reader counted metadata as data, every imported photo would read as "data differs".

The unit tests build JPEG marker layouts byte by byte, so the expected range is known
independently of the reader.
"""

import os
import struct
import subprocess
import sys
from pathlib import Path

from conftest import create_test_photo

SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.data_portion import data_bytes, data_ranges  # noqa: E402


def segment(code: int, payload: bytes) -> bytes:
    return bytes([0xFF, code]) + struct.pack(">H", 2 + len(payload)) + payload


def _run_pipeline_writers(path: Path):
    env = {**os.environ, "PATH": f"{SCRIPT_DIR / 'tools'}{os.pathsep}{os.environ['PATH']}"}
    for args in (
        ["tag-media.py", "--make", "Sony", "--model", "ILCE-7M5", "--apply"],
        ["fix-media-timestamp.py", "--timezone", "+09:00", "--infer-from-filename", "--apply"],
    ):
        result = subprocess.run([sys.executable, str(SCRIPT_DIR / args[0]), *args[1:], str(path)],
                                capture_output=True, text=True, env=env, cwd=SCRIPT_DIR)
        assert result.returncode == 0, f"{args[0]} failed: {result.stderr}"


def _data(path: Path) -> bytes:
    content = path.read_bytes()
    return b"".join(content[offset:offset + length] for offset, length in data_ranges(path))


def test_tag_and_fix_timestamp_leave_jpeg_data_unchanged(tmp_path):
    photo = tmp_path / "IMG_20250619_042028.jpg"
    create_test_photo(photo)
    before = {"size": photo.stat().st_size, "data": _data(photo)}

    _run_pipeline_writers(photo)

    after = {"size": photo.stat().st_size, "data": _data(photo)}
    assert after["size"] != before["size"], "Expected the writes to change the file"
    assert after["data"] == before["data"], \
        f"Expected the data portion unchanged: {len(before['data'])} bytes before, {len(after['data'])} after"


def test_jpeg_data_starts_at_start_of_scan(tmp_path):
    headers = b"\xff\xd8" + segment(0xE1, b"Exif\x00\x00" + bytes(40)) + segment(0xDB, bytes(65))
    scan = segment(0xDA, bytes(10)) + bytes(500) + b"\xff\xd9"
    photo = tmp_path / "a.jpg"
    photo.write_bytes(headers + scan)

    assert data_ranges(photo) == [(len(headers), len(scan))]


def test_bytes_after_the_main_image_are_data(tmp_path):
    """Appended images and camera trailers follow the main image's end marker."""
    headers = b"\xff\xd8" + segment(0xE0, bytes(14))
    rest = segment(0xDA, bytes(10)) + bytes(100) + b"\xff\xd9" + b"\xff\xd8" + bytes(300)
    photo = tmp_path / "a.jpg"
    photo.write_bytes(headers + rest)

    assert data_bytes(photo) == len(rest)


def test_jpeg_without_start_of_scan_has_no_data(tmp_path):
    photo = tmp_path / "a.jpg"
    photo.write_bytes(b"\xff\xd8" + segment(0xE1, bytes(40)))

    assert data_ranges(photo) is None


def test_other_formats_have_no_reader(tmp_path):
    raw = tmp_path / "a.arw"
    raw.write_bytes(b"II*\x00" + bytes(100))

    assert data_ranges(raw) is None
