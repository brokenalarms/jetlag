"""Footage of a QuickTime-family file: the bytes the camera recorded, apart from metadata.

An exiftool write rebuilds a QuickTime file. Every top-level box except `mdat` is
written first, then `mdat` is copied after them, so a card file laid out
`ftyp wide mdat moov <trailer>` becomes `ftyp moov uuid mdat <trailer>`. The footage
bytes are unchanged but almost every offset moves, so a whole-file size or hash can
never match the card. The footage is what stays the same: each `mdat` payload, in
order, plus any trailer after the last box (Insta360 appends one holding its
maker notes and gyro data).

Only the top-level box headers are read: a handful of reads of 8-16 bytes per file.
"""

from __future__ import annotations

import hashlib
import os
import struct

# A file is QuickTime-family when its first box is one of these. Old QuickTime
# files can open with `wide`, `free`, `mdat` or `moov` rather than `ftyp`.
_FIRST_BOX_TYPES = {b"ftyp", b"wide", b"free", b"skip", b"mdat", b"moov"}

# Top-level box types a camera or exiftool writes. One of these running past the end
# of the file is a truncated copy; any other oversized "box" is the start of a
# trailer whose first bytes happen to look like a box header.
_TOP_LEVEL_TYPES = _FIRST_BOX_TYPES | {
    b"uuid", b"moof", b"mfra", b"meta", b"pnot", b"sidx", b"styp", b"pdin", b"prft", b"emsg",
}

# Insta360 trailer footer: its last 32 bytes are this magic, and the trailer's own
# length, counted back from the end of the file, is a little-endian u32 40 bytes
# from the end (the layout exiftool's ProcessInsta360 reads).
_INSTA360_MAGIC = b"8db42d694ccc418790edff439fe026bf"
_INSTA360_FOOTER_LENGTH = 78

_HASH_CHUNK = 1 << 20


def _is_box_type(box_type: bytes) -> bool:
    return all(0x20 <= b <= 0x7E for b in box_type)


def _insta360_trailer_length(f, file_size: int) -> int:
    if file_size < _INSTA360_FOOTER_LENGTH:
        return 0
    f.seek(file_size - _INSTA360_FOOTER_LENGTH)
    footer = f.read(_INSTA360_FOOTER_LENGTH)
    if footer[-32:] != _INSTA360_MAGIC:
        return 0
    length = struct.unpack("<I", footer[38:42])[0]
    return length if _INSTA360_FOOTER_LENGTH <= length <= file_size else 0


def footage_ranges(path: str | os.PathLike) -> list[tuple[int, int]] | None:
    """The (offset, length) of each `mdat` payload and of any trailer, in file order.

    None when the file is not a readable QuickTime-family file: not QuickTime at
    all, no `mdat`, or a known box that runs past the end of the file (a truncated
    copy).
    A caller then has no footage to compare and falls back to the whole file.
    """
    with open(path, "rb") as f:
        return footage_ranges_of(f, os.fstat(f.fileno()).st_size)


def footage_ranges_of(f, file_size: int) -> list[tuple[int, int]] | None:
    """footage_ranges for an open file of the given size: any object with seek and read."""
    boxes_end = file_size - _insta360_trailer_length(f, file_size)
    ranges: list[tuple[int, int]] = []
    position = 0
    while position + 8 <= boxes_end:
        f.seek(position)
        header = f.read(16)
        size, box_type = struct.unpack(">I4s", header[:8])
        if not _is_box_type(box_type):
            break
        if position == 0 and box_type not in _FIRST_BOX_TYPES:
            return None
        header_length = 8
        if size == 1:
            if len(header) < 16:
                return None
            size = struct.unpack(">Q", header[8:16])[0]
            header_length = 16
        elif size == 0:
            size = boxes_end - position
        if size < header_length or position + size > boxes_end:
            if box_type in _TOP_LEVEL_TYPES:
                return None
            break
        if box_type == b"mdat":
            ranges.append((position + header_length, size - header_length))
        position += size
    if position == 0 or not ranges:
        return None
    if position < file_size:
        ranges.append((position, file_size - position))
    return ranges


def footage_bytes(path: str | os.PathLike) -> int | None:
    """Total footage size, from the box headers alone; None as for footage_ranges."""
    ranges = footage_ranges(path)
    return None if ranges is None else sum(length for _, length in ranges)


def footage_sha256(path: str | os.PathLike) -> str | None:
    """sha256 of the footage bytes in file order; None as for footage_ranges.

    Reads the whole footage, so it is for checking a copy, not for listing one.
    """
    ranges = footage_ranges(path)
    if ranges is None:
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for offset, length in ranges:
            f.seek(offset)
            remaining = length
            while remaining:
                chunk = f.read(min(_HASH_CHUNK, remaining))
                if not chunk:
                    return None
                digest.update(chunk)
                remaining -= len(chunk)
    return digest.hexdigest()
