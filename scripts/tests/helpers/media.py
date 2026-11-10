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
