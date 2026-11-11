"""A file's data portion: the bytes its camera recorded, apart from metadata.

jetlag's writes, and other tools', rewrite metadata and can move it around the file,
so a copy jetlag has written rarely matches its card file in total size. The data
portion is what stays the same, and is what verify-card compares and hashes. See
docs/specs/completed/verify-card.md, "What is hashed".

- QuickTime family (video): each `mdat` payload plus any trailer, from lib.footage.
- HEIF and AVIF stills: the extents of every image item in the file's item table
  (`iloc`), in item order. Not the `mdat` payload: a metadata write stores its Exif
  and XMP as items inside `mdat`, so that payload changes on every write.
- JPEG: from the first start-of-scan marker to the end of the file, so images and
  camera trailers appended after the main image are included.
- TIFF-based RAW (.arw, .dng): the strips or tiles of the full-size image, in strip
  order: a write can move them, so file order is not stable but strip order is.
- Fujifilm RAF: the raw data block the RAF header points to.

Any other format has no reader and returns None: the caller then has only the total
size to compare. Only headers are read: a few small reads per file.
"""

from __future__ import annotations

import hashlib
import os
import struct

from lib.footage import footage_ranges_of

_HASH_CHUNK = 1 << 20

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


_TIFF_TYPE_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8, 13: 4}
_NEW_SUBFILE_TYPE = 0x00FE
_IMAGE_WIDTH, _IMAGE_LENGTH = 0x0100, 0x0101
_STRIP_OFFSETS, _STRIP_BYTE_COUNTS = 0x0111, 0x0117
_TILE_OFFSETS, _TILE_BYTE_COUNTS = 0x0144, 0x0145
_SUB_IFDS = 0x014A
# A malformed file could point IFDs at each other; real files have a handful.
_MAX_IFDS = 64


def _tiff_values(f, endian: str, entry: tuple[int, int, bytes]) -> list[int] | None:
    field_type, count, raw = entry
    size = _TIFF_TYPE_SIZES.get(field_type)
    code = {3: "H", 4: "I", 13: "I", 1: "B"}.get(field_type)
    if size is None or code is None:
        return None
    if size * count > 4:
        f.seek(struct.unpack(endian + "I", raw)[0])
        raw = f.read(size * count)
        if len(raw) < size * count:
            return None
    return list(struct.unpack(f"{endian}{count}{code}", raw[:size * count]))


def _tiff_ifd(f, endian: str, offset: int, file_size: int):
    if offset < 8 or offset + 2 > file_size:
        return None, 0
    f.seek(offset)
    count = struct.unpack(endian + "H", f.read(2))[0]
    data = f.read(12 * count + 4)
    if len(data) < 12 * count + 4:
        return None, 0
    entries = {}
    for i in range(count):
        tag, field_type, n = struct.unpack(endian + "HHI", data[12 * i:12 * i + 8])
        entries[tag] = (field_type, n, data[12 * i + 8:12 * i + 12])
    return entries, struct.unpack(endian + "I", data[-4:])[0]


def _tiff_ranges(f, file_size: int) -> list[tuple[int, int]] | None:
    f.seek(0)
    header = f.read(8)
    endian = {b"II": "<", b"MM": ">"}.get(header[:2])
    if endian is None or struct.unpack(endian + "H", header[2:4])[0] != 42:
        return None
    pending = [struct.unpack(endian + "I", header[4:8])[0]]
    seen: set[int] = set()
    images = []
    while pending and len(seen) < _MAX_IFDS:
        offset = pending.pop(0)
        if offset in seen:
            continue
        seen.add(offset)
        entries, next_offset = _tiff_ifd(f, endian, offset, file_size)
        if entries is None:
            continue
        if next_offset:
            pending.append(next_offset)
        if _SUB_IFDS in entries:
            pending.extend(_tiff_values(f, endian, entries[_SUB_IFDS]) or [])
        offsets_tag, counts_tag = ((_TILE_OFFSETS, _TILE_BYTE_COUNTS) if _TILE_OFFSETS in entries
                                   else (_STRIP_OFFSETS, _STRIP_BYTE_COUNTS))
        if offsets_tag not in entries or counts_tag not in entries:
            continue
        subfile = (_tiff_values(f, endian, entries[_NEW_SUBFILE_TYPE]) or [0])[0] \
            if _NEW_SUBFILE_TYPE in entries else 0
        width = (_tiff_values(f, endian, entries[_IMAGE_WIDTH]) or [0])[0] if _IMAGE_WIDTH in entries else 0
        height = (_tiff_values(f, endian, entries[_IMAGE_LENGTH]) or [0])[0] if _IMAGE_LENGTH in entries else 0
        images.append((subfile & 1, -(width * height), len(images), entries, offsets_tag, counts_tag))
    if not images:
        return None
    # The full-size image: not a reduced-resolution one (subfile bit 0), then largest.
    *_, entries, offsets_tag, counts_tag = min(images)
    offsets = _tiff_values(f, endian, entries[offsets_tag])
    counts = _tiff_values(f, endian, entries[counts_tag])
    if not offsets or not counts or len(offsets) != len(counts):
        return None
    if any(o + n > file_size for o, n in zip(offsets, counts)):
        return None
    return list(zip(offsets, counts))


# Item types that hold metadata rather than image data.
_HEIF_METADATA_ITEMS = {b"Exif", b"mime", b"uri "}


def _boxes(f, start: int, end: int):
    """(type, payload offset, payload end) of each box between start and end."""
    position = start
    while position + 8 <= end:
        f.seek(position)
        header = f.read(16)
        size, box_type = struct.unpack(">I4s", header[:8])
        header_length = 8
        if size == 1:
            size, header_length = struct.unpack(">Q", header[8:16])[0], 16
        elif size == 0:
            size = end - position
        if size < header_length or position + size > end:
            return
        yield box_type, position + header_length, position + size
        position += size


def _read_uint(f, size: int) -> int:
    return int.from_bytes(f.read(size), "big") if size else 0


def _heif_ranges(f, meta_start: int, meta_end: int, file_size: int) -> list[tuple[int, int]] | None:
    # meta is a full box: version and flags come before its children.
    children = {t: (s, e) for t, s, e in _boxes(f, meta_start + 4, meta_end)}
    if b"iinf" not in children or b"iloc" not in children:
        return None

    start, _ = children[b"iinf"]
    f.seek(start)
    version = f.read(4)[0]
    _read_uint(f, 2 if version == 0 else 4)
    item_types: dict[int, bytes] = {}
    for box_type, payload, _end in _boxes(f, f.tell(), children[b"iinf"][1]):
        if box_type != b"infe":
            continue
        f.seek(payload)
        infe_version = f.read(4)[0]
        if infe_version < 2:
            continue
        item_id = _read_uint(f, 2 if infe_version == 2 else 4)
        _read_uint(f, 2)
        item_types[item_id] = f.read(4)

    idat_start = children[b"idat"][0] if b"idat" in children else None
    start, _ = children[b"iloc"]
    f.seek(start)
    version = f.read(4)[0]
    sizes = f.read(2)
    offset_size, length_size = sizes[0] >> 4, sizes[0] & 0x0F
    base_offset_size, index_size = sizes[1] >> 4, (sizes[1] & 0x0F) if version in (1, 2) else 0
    item_count = _read_uint(f, 4 if version == 2 else 2)
    items: list[tuple[int, list[tuple[int, int]]]] = []
    for _ in range(item_count):
        item_id = _read_uint(f, 4 if version == 2 else 2)
        method = _read_uint(f, 2) & 0x0F if version in (1, 2) else 0
        _read_uint(f, 2)
        base = _read_uint(f, base_offset_size)
        extents = []
        for _ in range(_read_uint(f, 2)):
            _read_uint(f, index_size)
            offset = _read_uint(f, offset_size)
            length = _read_uint(f, length_size)
            if method == 1:
                if idat_start is None:
                    return None
                extents.append((idat_start + base + offset, length))
            elif method == 0:
                extents.append((base + offset, length))
            else:
                return None
        if item_types.get(item_id) not in _HEIF_METADATA_ITEMS:
            items.append((item_id, extents))
    ranges = [extent for _, extents in sorted(items) for extent in extents]
    if not ranges or any(length == 0 or o + length > file_size for o, length in ranges):
        return None
    return ranges


def _is_iso_still(f, file_size: int) -> bool:
    """A HEIF or AVIF still: a top-level meta with no movie (moov) beside it."""
    top = {t for t, _, _ in _boxes(f, 0, file_size)}
    return b"ftyp" in top and b"meta" in top and b"moov" not in top


def _iso_still_ranges(f, file_size: int) -> list[tuple[int, int]] | None:
    meta = next((s, e) for t, s, e in _boxes(f, 0, file_size) if t == b"meta")
    return _heif_ranges(f, *meta, file_size)


_RAF_MAGIC = b"FUJIFILMCCD-RAW "
_RAF_DATA_POINTER = 100


def _raf_ranges(f, file_size: int) -> list[tuple[int, int]] | None:
    f.seek(_RAF_DATA_POINTER)
    pointer = f.read(8)
    if len(pointer) < 8:
        return None
    offset, length = struct.unpack(">II", pointer)
    if length == 0 or offset + length > file_size:
        return None
    return [(offset, length)]


def data_ranges(path: str | os.PathLike) -> list[tuple[int, int]] | None:
    """The (offset, length) of each part of the data portion, in the order they are read.

    None when the format has no reader, or the file is truncated or malformed.
    """
    with open(path, "rb") as f:
        return data_ranges_of(f, os.fstat(f.fileno()).st_size)


def _still_reader(f, file_size: int):
    """The ranges reader for a still image's format; None for anything else."""
    f.seek(0)
    start = f.read(16)
    if start[:2] == _JPEG_SOI:
        return _jpeg_ranges
    if start == _RAF_MAGIC:
        return _raf_ranges
    if start[:2] in (b"II", b"MM"):
        return _tiff_ranges
    if start[4:8] == b"ftyp" and _is_iso_still(f, file_size):
        return _iso_still_ranges
    return None


def data_ranges_of(f, file_size: int) -> list[tuple[int, int]] | None:
    """data_ranges for an open file of the given size: any object with seek and read,
    such as a file on another host read in small pieces."""
    reader = _still_reader(f, file_size) or footage_ranges_of
    return reader(f, file_size)


def is_still(path: str | os.PathLike) -> bool:
    """A photo in one of the formats above (JPEG, RAF, TIFF-based RAW, HEIF/AVIF),
    which has no length the way a recording does."""
    with open(path, "rb") as f:
        return _still_reader(f, os.fstat(f.fileno()).st_size) is not None


def data_bytes(path: str | os.PathLike) -> int | None:
    """Total size of the data portion; None as for data_ranges."""
    ranges = data_ranges(path)
    return None if ranges is None else sum(length for _, length in ranges)


def data_sha256(path: str | os.PathLike) -> str | None:
    """sha256 of the data portion, its ranges in order; None as for data_ranges.

    Reads the whole data portion, so it is for checking a copy, not for listing one.
    """
    ranges = data_ranges(path)
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
