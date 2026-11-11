"""Test media: real videos and photos, written with the metadata a test asks for.

Each kind is made once per session with ffmpeg and copied, so a test pays only for
the copy and its exiftool write.
"""

from __future__ import annotations

import atexit
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

from lib.exiftool import exiftool

_template_video: Path | None = None


def _ensure_template() -> Path:
    global _template_video
    if _template_video is None:
        d = tempfile.mkdtemp(prefix="pytest_video_template_")
        _template_video = Path(d) / "template.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=0.04",
            "-c:v", "libx264", "-t", "0.04", "-pix_fmt", "yuv420p",
            str(_template_video)
        ], capture_output=True, check=True)
        atexit.register(lambda: shutil.rmtree(d, ignore_errors=True))
    return _template_video


def create_test_video(path, **exif_tags):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_ensure_template(), str(path))
    if exif_tags:
        tag_args = [f"-{field}={value}" for field, value in exif_tags.items()]
        exiftool.write_tags(str(path), tag_args)


INSTA360_MAGIC = b"8db42d694ccc418790edff439fe026bf"
MAKER_NOTES_RECORD = 0x101
MODEL_TAG = 0x12
FOOTER_LENGTH = 78


def insta360_trailer(model: str) -> bytes:
    """A trailer holding one maker-notes record that names the camera model."""
    value = model.encode()
    record = bytes([MODEL_TAG, len(value)]) + value
    record_header = struct.pack("<HI", MAKER_NOTES_RECORD, len(record))
    trailer_length = len(record) + FOOTER_LENGTH
    footer = record_header + bytes(32) + struct.pack("<I", trailer_length) + bytes(4) + INSTA360_MAGIC
    assert len(footer) == FOOTER_LENGTH
    return record + footer


def create_insta360_file(path: Path, model: str) -> Path:
    create_test_video(path)
    with open(path, "ab") as f:
        f.write(insta360_trailer(model))
    return path


def create_insv_with_corrupted_trailer(path: Path, **exif_tags) -> Path:
    """A clip shaped like the Insta360 X6's: a valid trailer signature, an empty
    record table, and a stated length reaching back into the last atom, so
    exiftool refuses every metadata write as a corrupted Insta360 trailer."""
    create_test_video(path, **exif_tags)
    records = bytes(64)
    overlap = 16
    footer = bytes(38) + struct.pack("<I", len(records) + FOOTER_LENGTH + overlap) + bytes(4) + INSTA360_MAGIC
    assert len(footer) == FOOTER_LENGTH
    with open(path, "ab") as f:
        f.write(records + footer)
    return path


_refuses_corrupted_trailer: bool | None = None


def exiftool_refuses_corrupted_insta360_trailer() -> bool:
    """Whether the exiftool in use checks an Insta360 trailer before writing. The
    app ships 13.50, which does; Ubuntu's packaged 12.76, which CI installs, writes
    such a clip without a word, so the tests that need the real refusal skip there."""
    global _refuses_corrupted_trailer
    if _refuses_corrupted_trailer is None:
        d = tempfile.mkdtemp(prefix="pytest_insta360_probe_")
        clip = create_insv_with_corrupted_trailer(Path(d) / "probe.insv")
        result = subprocess.run(["exiftool", "-overwrite_original", "-Make=Probe", str(clip)],
                                capture_output=True, text=True)
        _refuses_corrupted_trailer = "Corrupted Insta360 trailer" in result.stderr
        shutil.rmtree(d, ignore_errors=True)
    return _refuses_corrupted_trailer


def create_motion_video(path):
    """A video with a second track whose handler names it gyro data, as a camera's
    motion track is named. ExifTool reads it from the header exactly as it reads a
    Sony rtmd or GoPro gpmd track, without the test shipping real camera footage."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        subtitles = Path(d) / "track.srt"
        subtitles.write_text("1\n00:00:00,000 --> 00:00:00,040\n.\n")
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=0.04",
            "-i", str(subtitles),
            "-c:v", "libx264", "-t", "0.04", "-pix_fmt", "yuv420p",
            "-c:s", "mov_text", "-metadata:s:s:0", "handler_name=Gyro Motion Data",
            str(path),
        ], capture_output=True, check=True)


_template_photo: Path | None = None


def _ensure_template_photo() -> Path:
    """A real JPEG. The MP4 template has no ExifIFD group, so binary-EXIF stills
    tags such as OffsetTimeOriginal cannot round-trip through it at all."""
    global _template_photo
    if _template_photo is None:
        d = tempfile.mkdtemp(prefix="pytest_photo_template_")
        _template_photo = Path(d) / "template.jpg"
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x48:d=0.04",
            "-frames:v", "1", str(_template_photo)
        ], capture_output=True, check=True)
        atexit.register(lambda: shutil.rmtree(d, ignore_errors=True))
    return _template_photo


def create_test_photo(path, **exif_tags):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_ensure_template_photo(), str(path))
    if exif_tags:
        tag_args = [f"-{field}={value}" for field, value in exif_tags.items()]
        exiftool.write_tags(str(path), tag_args)


def create_test_tiff_raw(path) -> Path:
    """A TIFF-based raw file laid out as cameras write them: IFD0 holds a reduced-size
    preview strip and points, through SubIFDs, at the full-size image in two strips.
    Carries a DNGVersion so exiftool will write it as .dng as well as .arw."""
    endian = "<"
    preview, strip1, strip2 = bytes(range(256)) * 4, bytes([7]) * 3000, bytes([9]) * 2500

    def ifd(entries):
        body = struct.pack(endian + "H", len(entries))
        for tag, field_type, count, value in sorted(entries):
            body += struct.pack(endian + "HHI", tag, field_type, count) + value
        return body + struct.pack(endian + "I", 0)

    def short(v):
        return struct.pack(endian + "HH", v, 0)

    def long(v):
        return struct.pack(endian + "I", v)

    sub_offset = 8 + 2 + 12 * 11 + 4
    arrays = sub_offset + 2 + 12 * 7 + 4
    preview_offset = arrays + 16
    strip1_offset = preview_offset + len(preview)
    strip2_offset = strip1_offset + len(strip1)
    ifd0 = ifd([
        (0x00FE, 4, 1, long(1)), (0x0100, 3, 1, short(32)), (0x0101, 3, 1, short(32)),
        (0x0103, 3, 1, short(1)), (0x0106, 3, 1, short(2)), (0x0111, 4, 1, long(preview_offset)),
        (0x0115, 3, 1, short(1)), (0x0116, 3, 1, short(32)), (0x0117, 4, 1, long(len(preview))),
        (0x014A, 4, 1, long(sub_offset)), (0xC612, 1, 4, bytes([1, 4, 0, 0])),
    ])
    full_size = ifd([
        (0x00FE, 4, 1, long(0)), (0x0100, 3, 1, short(100)), (0x0101, 3, 1, short(55)),
        (0x0103, 3, 1, short(1)), (0x0111, 4, 2, long(arrays)), (0x0116, 3, 1, short(30)),
        (0x0117, 4, 2, long(arrays + 8)),
    ])
    content = (b"II*\x00" + long(8) + ifd0 + full_size
               + struct.pack(endian + "IIII", strip1_offset, strip2_offset, len(strip1), len(strip2))
               + preview + strip1 + strip2)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(content)
    return Path(path)


def create_test_raf(path) -> Path:
    """A Fujifilm RAF: the 0x94-byte header exiftool checks, the embedded JPEG it
    rewrites, an empty RAF directory, then the raw data the header points to at 0x64."""
    jpeg = _ensure_template_photo().read_bytes()
    jpeg += b"\x00" * ((4 - len(jpeg) % 4) % 4)
    raw = bytes(range(200)) * 20
    header = bytearray(0x94)
    header[0:16] = b"FUJIFILMCCD-RAW "
    header[16:28] = b"0201FF383501"
    header[28:60] = b"X-T5".ljust(32, b"\x00")
    header[0x3C:0x40] = b"0100"
    jpeg_offset = 0x94
    directory_offset = jpeg_offset + len(jpeg)
    raw_offset = directory_offset + 4
    header[0x54:0x5C] = struct.pack(">II", jpeg_offset, len(jpeg))
    header[0x5C:0x64] = struct.pack(">II", directory_offset, 4)
    header[0x64:0x6C] = struct.pack(">II", raw_offset, len(raw))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(bytes(header) + jpeg + struct.pack(">I", 0) + raw)
    return Path(path)


def create_test_heif(path) -> Path:
    """A one-item AVIF still from ffmpeg: the same item-table structure (meta, iinf,
    iloc, mdat) as a camera's HEIF, which ffmpeg cannot encode."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=gray:s=64x64:d=0.04",
        "-frames:v", "1", "-f", "avif", str(path),
    ], capture_output=True, check=True)
    return Path(path)
