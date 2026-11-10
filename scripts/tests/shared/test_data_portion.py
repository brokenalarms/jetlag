#!/usr/bin/env python3
"""
verify-card compares a photo jetlag has written with its card file by the photo's data
portion, because a metadata write changes the file's total size and can move the image
data within it. Per format: a JPEG from its first start-of-scan marker to the end; a
TIFF-based raw file (.arw, .dng) its full-size image strips; a RAF the raw block its
header points to; a HEIF or AVIF still the extents of its image items.

The regression test runs the pipeline's own writers (tag-media, then
fix-media-timestamp) on each format and requires its data portion to be what it was,
while the file around it has visibly changed. If a writer touched the image data, or
the reader counted metadata as data, every imported photo of that format would read as
"data differs" on every backup location.

The unit tests build layouts byte by byte, so the expected range is known
independently of the reader.
"""

import os
import struct
import subprocess
import sys
from pathlib import Path

from helpers import SCRIPT_DIR
import pytest

from helpers.media import create_test_heif, create_test_photo, create_test_raf, create_test_tiff_raw
from lib.data_portion import data_bytes, data_ranges


def segment(code: int, payload: bytes) -> bytes:
    return bytes([0xFF, code]) + struct.pack(">H", 2 + len(payload)) + payload


def _run_pipeline_writers(path: Path):
    env = {**os.environ, "PATH": f"{SCRIPT_DIR / 'tools'}{os.pathsep}{os.environ['PATH']}"}
    for args in (
        ["cli/tag_media.py", "--make", "Sony", "--model", "ILCE-7M5", "--apply"],
        ["cli/fix_media_timestamp.py", "--timezone", "+09:00", "--infer-from-filename", "--apply"],
    ):
        result = subprocess.run([sys.executable, str(SCRIPT_DIR / args[0]), *args[1:], str(path)],
                                capture_output=True, text=True, env=env, cwd=SCRIPT_DIR)
        assert result.returncode == 0, f"{args[0]} failed: {result.stderr}"


def _data(path: Path) -> bytes:
    content = path.read_bytes()
    return b"".join(content[offset:offset + length] for offset, length in data_ranges(path))


PHOTO_FORMATS = {
    ".jpg": create_test_photo,
    ".arw": create_test_tiff_raw,
    ".dng": create_test_tiff_raw,
    ".raf": create_test_raf,
    ".avif": create_test_heif,
}


@pytest.mark.parametrize("suffix", sorted(PHOTO_FORMATS))
def test_tag_and_fix_timestamp_leave_the_data_portion_unchanged(tmp_path, suffix):
    photo = tmp_path / f"IMG_20250619_042028{suffix}"
    PHOTO_FORMATS[suffix](photo)
    before = {"size": photo.stat().st_size, "data": _data(photo)}

    _run_pipeline_writers(photo)

    after = {"size": photo.stat().st_size, "data": _data(photo)}
    assert after["size"] != before["size"], "Expected the writes to change the file"
    assert before["data"], "Expected a data portion on the card file"
    assert after["data"] == before["data"], \
        f"Expected the data portion unchanged: {len(before['data'])} bytes before, {len(after['data'])} after"


@pytest.mark.parametrize("suffix", [".arw", ".raf", ".avif"])
def test_writes_move_the_data_so_offsets_are_read_not_assumed(tmp_path, suffix):
    """The writes put metadata ahead of the image data, so a reader that assumed the
    card's offsets would read the wrong bytes."""
    photo = tmp_path / f"IMG_20250619_042028{suffix}"
    PHOTO_FORMATS[suffix](photo)
    before = data_ranges(photo)

    _run_pipeline_writers(photo)

    assert data_ranges(photo) != before


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


def test_tiff_raw_data_is_the_full_size_image_not_the_preview(tmp_path):
    raw = create_test_tiff_raw(tmp_path / "a.arw")
    content = raw.read_bytes()

    ranges = data_ranges(raw)

    assert [content[o:o + n][:1] for o, n in ranges] == [bytes([7]), bytes([9])]
    assert [n for _, n in ranges] == [3000, 2500]


def test_raf_data_is_the_block_its_header_points_to(tmp_path):
    raf = create_test_raf(tmp_path / "a.raf")
    content = raf.read_bytes()
    offset, length = struct.unpack(">II", content[0x64:0x6C])

    assert data_ranges(raf) == [(offset, length)]


def test_heif_metadata_items_are_not_data(tmp_path):
    """exiftool stores Exif as an item inside mdat; it must not count as data."""
    still = create_test_heif(tmp_path / "a.avif")
    before = data_bytes(still)
    subprocess.run([str(SCRIPT_DIR / "tools" / "exiftool"), "-overwrite_original",
                    "-Make=Sony", str(still)], capture_output=True, check=True)

    assert data_bytes(still) == before
