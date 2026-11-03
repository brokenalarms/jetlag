#!/usr/bin/env python3
"""
Verify-card matches an imported copy to its card file by footage size, because an
exiftool write rebuilds a QuickTime file and moves almost every byte: the card's
`ftyp wide mdat moov` becomes `ftyp moov uuid mdat`. Only the `mdat` payload and any
trailer after the last box survive unchanged.

The regression test runs the pipeline's own writers (tag-media, then
fix-media-timestamp) on a card-layout file of each video format a profile imports,
and requires the footage size and hash to be what they were on the card, while the
file around them has visibly been rebuilt. If a writer ever touched the footage, or
the reader counted metadata as footage, every imported file would read as
"footage differs" on every backup location.

The unit tests build box layouts byte by byte, so the expected footage is known
independently of the reader.
"""

import hashlib
import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import create_insta360_file, create_test_photo, create_test_video, insta360_trailer

SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.footage import footage_bytes, footage_ranges, footage_sha256


def box(box_type: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), box_type) + payload


def large_box(box_type: bytes, payload: bytes) -> bytes:
    """A box with a 64-bit size, as cameras write for an mdat over 4 GB."""
    return struct.pack(">I4sQ", 1, box_type, 16 + len(payload)) + payload


FTYP = box(b"ftyp", b"isom\x00\x00\x02\x00isomiso2avc1mp41")
MOOV = box(b"moov", box(b"mvhd", bytes(100)))
FOOTAGE = bytes(range(256)) * 40


def top_level_layout(path: Path) -> list[str]:
    """Top-level box types in order, read independently of lib.footage."""
    data = path.read_bytes()
    layout, position = [], 0
    while position + 8 <= len(data):
        size, box_type = struct.unpack(">I4s", data[position:position + 8])
        if size < 8 or position + size > len(data) or not box_type.isascii():
            break
        layout.append(box_type.decode())
        position += size
    return layout


# --- regression: the pipeline's writes leave the footage untouched -------------

def _card_mp4(path: Path) -> Path:
    create_test_video(path)
    return path


def _card_mov(path: Path) -> Path:
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=0.04",
        "-c:v", "libx264", "-t", "0.04", "-pix_fmt", "yuv420p", str(path),
    ], capture_output=True, check=True)
    return path


def _card_insv(path: Path) -> Path:
    return create_insta360_file(path, "Insta360 X4")


# The video formats media-profiles.yaml imports, each laid out as the camera
# writes it: mdat before moov, the Insta360 trailer after the last box.
CARD_FORMATS = {
    ".mp4": _card_mp4,
    ".mov": _card_mov,
    ".insv": _card_insv,
}


def _run_pipeline_writers(path: Path):
    env = {**os.environ, "PATH": f"{SCRIPT_DIR / 'tools'}{os.pathsep}{os.environ['PATH']}"}
    for args in (
        ["tag-media.py", "--make", "Sony", "--model", "ILCE-7M5", "--apply"],
        ["fix-media-timestamp.py", "--timezone", "+09:00", "--infer-from-filename", "--apply"],
    ):
        result = subprocess.run([sys.executable, str(SCRIPT_DIR / args[0]), *args[1:], str(path)],
                                capture_output=True, text=True, env=env, cwd=SCRIPT_DIR)
        assert result.returncode == 0, f"{args[0]} failed: {result.stderr}"


@pytest.mark.parametrize("suffix", sorted(CARD_FORMATS))
def test_tag_and_fix_timestamp_leave_footage_unchanged(tmp_path, suffix):
    card = CARD_FORMATS[suffix](tmp_path / f"VID_20250619_042028_00_004{suffix}")
    before = {
        "layout": top_level_layout(card),
        "file_sha256": hashlib.sha256(card.read_bytes()).hexdigest(),
        "footage_bytes": footage_bytes(card),
        "footage_sha256": footage_sha256(card),
    }

    _run_pipeline_writers(card)

    after = {
        "layout": top_level_layout(card),
        "file_sha256": hashlib.sha256(card.read_bytes()).hexdigest(),
        "footage_bytes": footage_bytes(card),
        "footage_sha256": footage_sha256(card),
    }
    # The file really was rebuilt, so an unchanged footage hash means something.
    assert before["layout"].index("mdat") < before["layout"].index("moov"), f"card: {before['layout']}"
    assert after["layout"].index("moov") < after["layout"].index("mdat"), f"imported: {after['layout']}"
    assert after["file_sha256"] != before["file_sha256"], "Expected the writes to change the file"
    assert before["footage_bytes"] is not None
    assert (after["footage_bytes"], after["footage_sha256"]) == (before["footage_bytes"], before["footage_sha256"]), \
        f"Expected footage unchanged by the writes. Before: {before}, After: {after}"


def test_insta360_trailer_is_part_of_the_footage(tmp_path):
    """The trailer holds the camera's gyro data, which no write may change, so it
    counts as footage: two copies with equal mdat but a different trailer differ."""
    plain = tmp_path / "plain.mp4"
    create_test_video(plain)
    insv = create_insta360_file(tmp_path / "VID_0001.insv", "Insta360 X4")

    trailer = insta360_trailer("Insta360 X4")
    assert footage_bytes(insv) == footage_bytes(plain) + len(trailer), \
        f"Actual: {footage_bytes(insv)}, Expected: {footage_bytes(plain)} + {len(trailer)}"
    assert footage_sha256(insv) != footage_sha256(plain)


# --- reader: box layouts built byte by byte -----------------------------------

def test_footage_is_mdat_payload_wherever_mdat_sits(tmp_path):
    card = tmp_path / "card.mp4"
    imported = tmp_path / "imported.mp4"
    card.write_bytes(FTYP + box(b"wide", b"") + box(b"mdat", FOOTAGE) + MOOV)
    imported.write_bytes(FTYP + MOOV + box(b"uuid", bytes(500)) + box(b"mdat", FOOTAGE))

    assert footage_bytes(card) == footage_bytes(imported) == len(FOOTAGE)
    assert footage_sha256(card) == footage_sha256(imported) == hashlib.sha256(FOOTAGE).hexdigest()


def test_64_bit_mdat_header_is_not_footage(tmp_path):
    """A camera writes a 16-byte mdat header for files over 4 GB; exiftool may keep it
    or not, so only the payload counts."""
    video = tmp_path / "large.mp4"
    video.write_bytes(FTYP + large_box(b"mdat", FOOTAGE) + MOOV)

    assert footage_ranges(video) == [(len(FTYP) + 16, len(FOOTAGE))]


def test_mdat_with_size_zero_runs_to_end_of_file(tmp_path):
    video = tmp_path / "open.mp4"
    video.write_bytes(FTYP + MOOV + struct.pack(">I4s", 0, b"mdat") + FOOTAGE)

    assert footage_bytes(video) == len(FOOTAGE)


def test_every_mdat_counts_in_file_order(tmp_path):
    video = tmp_path / "fragmented.mp4"
    first, second = FOOTAGE[:1000], FOOTAGE[1000:]
    video.write_bytes(FTYP + MOOV + box(b"mdat", first) + box(b"moof", bytes(20)) + box(b"mdat", second))

    assert footage_bytes(video) == len(FOOTAGE)
    assert footage_sha256(video) == hashlib.sha256(FOOTAGE).hexdigest()


def test_bytes_after_the_last_box_are_a_trailer(tmp_path):
    trailer = b"\x00\x01trailer-without-a-known-footer"
    video = tmp_path / "trailer.mp4"
    video.write_bytes(FTYP + box(b"mdat", FOOTAGE) + MOOV + trailer)

    assert footage_sha256(video) == hashlib.sha256(FOOTAGE + trailer).hexdigest()


def test_truncated_copy_has_no_footage(tmp_path):
    """A copy cut short mid-mdat is not a smaller footage, it is unreadable: the
    caller falls back to comparing whole files, which also fails."""
    video = tmp_path / "truncated.mp4"
    video.write_bytes((FTYP + MOOV + box(b"mdat", FOOTAGE))[:-100])

    assert footage_ranges(video) is None


def test_non_quicktime_file_has_no_footage(tmp_path):
    photo = tmp_path / "photo.jpg"
    create_test_photo(photo)

    assert footage_ranges(photo) is None


def test_quicktime_without_mdat_has_no_footage(tmp_path):
    video = tmp_path / "empty.mp4"
    video.write_bytes(FTYP + MOOV)

    assert footage_ranges(video) is None
