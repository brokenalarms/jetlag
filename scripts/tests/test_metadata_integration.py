"""
Integration tests for the jetlag-metadata Swift CLI.

Verifies that the jetlag-metadata binary produces identical results to direct
ExifTool invocation for every operation the CLI supports: reading timestamps,
reading camera info, writing timestamps, and writing camera info. Each test
creates a real media file, runs the operation through the CLI's JSON protocol,
and compares the result to a ground-truth ExifTool read.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from conftest import create_test_video

REPO_ROOT = Path(__file__).parent.parent.parent
JETLAG_METADATA_PKG = REPO_ROOT / "macos" / "Sources" / "Tools" / "jetlag-metadata"
JETLAG_METADATA_BIN = JETLAG_METADATA_PKG / ".build" / "release" / "jetlag-metadata"


def _build_jetlag_metadata():
    """Build the jetlag-metadata binary and ensure exiftool is discoverable."""
    if not JETLAG_METADATA_BIN.exists():
        result = subprocess.run(
            ["swift", "build", "-c", "release"],
            cwd=str(JETLAG_METADATA_PKG),
            capture_output=True,
            timeout=120,
        )
        if result.returncode != 0 or not JETLAG_METADATA_BIN.exists():
            return False

    exiftool_path = shutil.which("exiftool")
    if not exiftool_path:
        return False
    adjacent_exiftool = JETLAG_METADATA_BIN.parent / "exiftool"
    if not adjacent_exiftool.exists():
        adjacent_exiftool.symlink_to(exiftool_path)
    return True


if not _build_jetlag_metadata():
    pytest.skip(
        "jetlag-metadata binary could not be built (requires Swift toolchain)",
        allow_module_level=True,
    )


def cli_request(request_obj: dict) -> dict:
    """Send a single JSON request to jetlag-metadata and return the response."""
    proc = subprocess.run(
        [str(JETLAG_METADATA_BIN)],
        input=json.dumps(request_obj) + "\n",
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0, f"jetlag-metadata crashed: {proc.stderr}"
    lines = [l for l in proc.stdout.strip().splitlines() if l.strip()]
    assert len(lines) == 1, f"Expected 1 response line, got {len(lines)}: {lines}"
    return json.loads(lines[0])


def exiftool_read(file_path: str, tags: list[str]) -> dict:
    """Read tags from a file using exiftool directly."""
    args = ["exiftool", "-s"] + [f"-{t}" for t in tags] + [file_path]
    result = subprocess.run(args, capture_output=True, text=True, timeout=15)
    data = {}
    for line in result.stdout.strip().splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip()
    return data


@pytest.fixture
def temp_dir():
    tmpdir = tempfile.mkdtemp(prefix="test_metadata_int_")
    yield tmpdir
    shutil.rmtree(tmpdir)


class TestReadTimestamps:
    """Reading timestamp tags through jetlag-metadata matches direct ExifTool output."""

    def test_read_datetime_original(self, temp_dir):
        """A video with DateTimeOriginal returns the same value from both backends."""
        video = os.path.join(temp_dir, "ts.mp4")
        create_test_video(video, DateTimeOriginal="2025:06:18 07:25:21+08:00")

        cli_result = cli_request({
            "op": "read",
            "file": video,
            "tags": ["DateTimeOriginal"],
        })
        exif_result = exiftool_read(video, ["DateTimeOriginal"])

        assert "DateTimeOriginal" in cli_result
        assert cli_result["DateTimeOriginal"] == exif_result["DateTimeOriginal"]

    def test_read_multiple_timestamp_tags(self, temp_dir):
        """Reading several timestamp tags at once returns all of them consistently."""
        video = os.path.join(temp_dir, "multi_ts.mp4")
        create_test_video(
            video,
            DateTimeOriginal="2025:06:18 07:25:21+08:00",
            CreateDate="2025:06:18 07:25:21+08:00",
            ModifyDate="2025:06:18 07:25:21+08:00",
        )

        tags = ["DateTimeOriginal", "CreateDate", "ModifyDate"]
        cli_result = cli_request({"op": "read", "file": video, "tags": tags})
        exif_result = exiftool_read(video, tags)

        for tag in tags:
            assert tag in cli_result, f"CLI missing {tag}"
            assert cli_result[tag] == exif_result[tag], (
                f"{tag}: CLI={cli_result[tag]} vs ExifTool={exif_result[tag]}"
            )

    def test_read_with_fast_mode(self, temp_dir):
        """Fast mode reads still return correct timestamp data."""
        video = os.path.join(temp_dir, "fast.mp4")
        create_test_video(video, DateTimeOriginal="2025:01:01 00:00:00")

        cli_result = cli_request({
            "op": "read",
            "file": video,
            "tags": ["DateTimeOriginal"],
            "fast": True,
        })

        assert "DateTimeOriginal" in cli_result
        assert "2025:01:01" in cli_result["DateTimeOriginal"]


class TestReadCamera:
    """Reading camera Make/Model through jetlag-metadata matches direct ExifTool."""

    def test_read_make_and_model(self, temp_dir):
        """Camera Make and Model are returned identically to ExifTool."""
        video = os.path.join(temp_dir, "cam.mp4")
        create_test_video(video, Make="GoPro", Model="HERO12 Black")

        cli_result = cli_request({
            "op": "read",
            "file": video,
            "tags": ["Make", "Model"],
        })
        exif_result = exiftool_read(video, ["Make", "Model"])

        assert cli_result["Make"] == exif_result["Make"]
        assert cli_result["Model"] == exif_result["Model"]

    def test_read_missing_camera_tags(self, temp_dir):
        """A file with no camera tags returns an empty result for those tags."""
        video = os.path.join(temp_dir, "nocam.mp4")
        create_test_video(video)

        cli_result = cli_request({
            "op": "read",
            "file": video,
            "tags": ["Make", "Model"],
        })

        assert "Make" not in cli_result or cli_result["Make"] == ""
        assert "Model" not in cli_result or cli_result["Model"] == ""


class TestWriteTimestamps:
    """Writing timestamp tags and verifying them via ExifTool ground-truth read."""

    def test_write_datetime_original(self, temp_dir):
        """Writing DateTimeOriginal is reflected in a subsequent ExifTool read."""
        video = os.path.join(temp_dir, "wts.mp4")
        create_test_video(video)

        before = exiftool_read(video, ["DateTimeOriginal"])

        result = cli_request({
            "op": "write",
            "file": video,
            "tags": {"DateTimeOriginal": "2024:12:25 15:30:00"},
        })
        assert result["updated"] is True

        after = exiftool_read(video, ["DateTimeOriginal"])
        assert after["DateTimeOriginal"] == "2024:12:25 15:30:00"
        assert after["DateTimeOriginal"] != before.get("DateTimeOriginal", "")

    def test_write_multiple_timestamps(self, temp_dir):
        """Writing several timestamp tags at once persists all of them."""
        video = os.path.join(temp_dir, "wmulti.mp4")
        create_test_video(video)

        ts = "2024:07:04 12:00:00+05:00"
        result = cli_request({
            "op": "write",
            "file": video,
            "tags": {
                "DateTimeOriginal": ts,
                "CreateDate": ts,
                "ModifyDate": ts,
            },
        })
        assert result["updated"] is True

        after = exiftool_read(video, ["DateTimeOriginal", "CreateDate", "ModifyDate"])
        for tag in ["DateTimeOriginal", "CreateDate", "ModifyDate"]:
            assert "2024:07:04 12:00:00" in after[tag]

    def test_write_group_prefixed_tag(self, temp_dir):
        """Writing a group-prefixed tag like Keys:CreationDate works correctly."""
        video = os.path.join(temp_dir, "wgroup.mov")
        create_test_video(video)

        result = cli_request({
            "op": "write",
            "file": video,
            "tags": {"Keys:CreationDate": "2024:03:15 09:00:00"},
        })
        assert result["updated"] is True

        after = exiftool_read(video, ["CreationDate"])
        assert "2024:03:15" in after.get("CreationDate", "")


class TestWriteCamera:
    """Writing camera Make/Model and verifying them via ExifTool ground-truth read."""

    def test_write_make_and_model(self, temp_dir):
        """Writing Make and Model is reflected in a subsequent ExifTool read."""
        video = os.path.join(temp_dir, "wcam.mp4")
        create_test_video(video)

        result = cli_request({
            "op": "write",
            "file": video,
            "tags": {"Make": "Sony", "Model": "A7IV"},
        })
        assert result["updated"] is True

        after = exiftool_read(video, ["Make", "Model"])
        assert after["Make"] == "Sony"
        assert after["Model"] == "A7IV"

    def test_overwrite_existing_camera(self, temp_dir):
        """Overwriting existing camera tags replaces old values."""
        video = os.path.join(temp_dir, "wcam_over.mp4")
        create_test_video(video, Make="OldMake", Model="OldModel")

        before = exiftool_read(video, ["Make", "Model"])
        assert before["Make"] == "OldMake"

        result = cli_request({
            "op": "write",
            "file": video,
            "tags": {"Make": "NewMake", "Model": "NewModel"},
        })
        assert result["updated"] is True

        after = exiftool_read(video, ["Make", "Model"])
        assert after["Make"] == "NewMake"
        assert after["Model"] == "NewModel"


class TestRoundTrip:
    """Write tags through jetlag-metadata, read them back through it, and verify
    both sides agree with ExifTool ground truth."""

    def test_full_round_trip(self, temp_dir):
        """Write all supported tags, then read them back through both backends."""
        video = os.path.join(temp_dir, "roundtrip.mp4")
        create_test_video(video)

        tags_to_write = {
            "DateTimeOriginal": "2024:06:15 14:30:00",
            "Make": "Canon",
            "Model": "EOS R5",
        }

        write_result = cli_request({
            "op": "write",
            "file": video,
            "tags": tags_to_write,
        })
        assert write_result["updated"] is True

        cli_read = cli_request({
            "op": "read",
            "file": video,
            "tags": list(tags_to_write.keys()),
        })
        exif_read = exiftool_read(video, list(tags_to_write.keys()))

        for tag, expected in tags_to_write.items():
            assert tag in cli_read, f"CLI read missing {tag}"
            assert cli_read[tag] == exif_read[tag], (
                f"{tag}: CLI={cli_read[tag]} vs ExifTool={exif_read[tag]}"
            )
            assert expected in cli_read[tag], (
                f"{tag}: expected '{expected}' in '{cli_read[tag]}'"
            )
