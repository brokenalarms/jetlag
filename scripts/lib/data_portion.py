"""A file's data portion: the bytes its camera recorded, apart from metadata.

jetlag's writes, and other tools', rewrite metadata and can move it around the file,
so a copy jetlag has written rarely matches its card file in total size. The data
portion is what stays the same, and is what verify-card compares and hashes. See
docs/specs/verify-card.md, "What is hashed".

- QuickTime family and HEIF (ISO base media): each `mdat` payload plus any trailer,
  from lib.footage.
- JPEG: from the first start-of-scan marker to the end of the file, so images and
  camera trailers appended after the main image are included.

Any other format has no reader yet and returns None: the caller then has only the
total size to compare. Only headers are read: a few small reads per file.
"""

from __future__ import annotations

import os
import struct

from lib.footage import footage_ranges

_JPEG_SOI = b"\xff\xd8"
_JPEG_SOS = 0xDA
# Markers that stand alone, with no length field after them.
_JPEG_STANDALONE = {0x01, *range(0xD0, 0xD8)}


def _jpeg_ranges(f, file_size: int) -> list[tuple[int, int]] | None:
    position = 2
    while position + 4 <= file_size:
        f.seek(position)
        marker = f.read(2)
        if marker[0] != 0xFF:
            return None
        code = marker[1]
        if code == 0xFF:
            # Fill byte before a marker.
            position += 1
            continue
        if code == _JPEG_SOS:
            return [(position, file_size - position)]
        if code in _JPEG_STANDALONE:
            position += 2
            continue
        length = struct.unpack(">H", f.read(2))[0]
        if length < 2:
            return None
        position += 2 + length
    return None


def data_ranges(path: str | os.PathLike) -> list[tuple[int, int]] | None:
    """The (offset, length) of each part of the data portion, in file order.

    None when the format has no reader, or the file is truncated or malformed.
    """
    with open(path, "rb") as f:
        file_size = os.fstat(f.fileno()).st_size
        if f.read(2) == _JPEG_SOI:
            return _jpeg_ranges(f, file_size)
    return footage_ranges(path)


def data_bytes(path: str | os.PathLike) -> int | None:
    """Total size of the data portion; None as for data_ranges."""
    ranges = data_ranges(path)
    return None if ranges is None else sum(length for _, length in ranges)
