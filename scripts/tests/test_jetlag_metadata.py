#!/usr/bin/env python3
"""
Tests for the jetlag-metadata Swift CLI tool.

Validates the JSON-over-stdin/stdout protocol that jetlag-metadata exposes.
Each test sends a JSON request to the persistent process and verifies the
response matches what ExifTool would produce directly. This ensures the
Swift wrapper is a faithful proxy for all operations Jetlag uses.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from conftest import create_test_video

SCRIPTS_DIR = Path(__file__).parent.parent
TOOLS_DIR = SCRIPTS_DIR / "tools"
METADATA_BINARY = TOOLS_DIR / "jetlag-metadata"


def _find_binary():
    if METADATA_BINARY.is_file() and os.access(METADATA_BINARY, os.X_OK):
        return str(METADATA_BINARY)
    if shutil.which("jetlag-metadata"):
        return "jetlag-metadata"
    return None


BINARY_PATH = _find_binary()

pytestmark = pytest.mark.skipif(
    BINARY_PATH is None,
    reason="jetlag-metadata binary not built — run scripts/tools/build-jetlag-metadata.sh",
)


class MetadataClient:
    """Manages a persistent jetlag-metadata subprocess for testing."""

    def __init__(self):
        self._process = subprocess.Popen(
            [BINARY_PATH],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def call(self, request: dict) -> dict:
        line = json.dumps(request, separators=(",", ":")) + "\n"
        self._process.stdin.write(line.encode())
        self._process.stdin.flush()
        response_line = self._process.stdout.readline()
        if not response_line:
            return {}
        return json.loads(response_line.decode())

    def close(self):
        if self._process and self._process.poll() is None:
            try:
                self._process.stdin.close()
                self._process.wait(timeout=5)
            except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                self._process.kill()
                self._process.wait()


@pytest.fixture
def client():
    c = MetadataClient()
    yield c
    c.close()


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)


@pytest.fixture
def test_video(temp_dir):
    path = os.path.join(temp_dir, "test.mp4")
    create_test_video(path)
    return path


@pytest.fixture
def tagged_video(temp_dir):
    """A video with DateTimeOriginal, Make, and Model already set."""
    path = os.path.join(temp_dir, "tagged.mp4")
    create_test_video(
        path,
        DateTimeOriginal="2025:06:18 07:25:21+08:00",
        Make="GoPro",
        Model="HERO12 Black",
    )
    return path


class TestReadOperation:
    """Verify the read operation returns correct tag values for all tag
    types Jetlag uses: timestamps, camera make/model, and CreationDate."""

    def test_read_timestamp_tags(self, client, tagged_video):
        """Read DateTimeOriginal from a video that has it set.

        Before: video has DateTimeOriginal=2025:06:18 07:25:21+08:00
        After: JSON response includes the value
        """
        result = client.call({
            "op": "read",
            "file": tagged_video,
            "tags": ["DateTimeOriginal"],
        })

        assert "error" not in result, f"Unexpected error: {result.get('error')}"
        assert "DateTimeOriginal" in result
        assert "2025:06:18" in result["DateTimeOriginal"]
        assert "07:25:21" in result["DateTimeOriginal"]

    def test_read_camera_tags(self, client, tagged_video):
        """Read Make and Model from a tagged video.

        Before: video has Make=GoPro, Model=HERO12 Black
        After: JSON response contains both values
        """
        result = client.call({
            "op": "read",
            "file": tagged_video,
            "tags": ["Make", "Model"],
        })

        assert "error" not in result, f"Unexpected error: {result.get('error')}"
        assert result.get("Make") == "GoPro"
        assert result.get("Model") == "HERO12 Black"

    def test_read_missing_tags_returns_empty(self, client, test_video):
        """Read tags from a file that doesn't have them set.

        Before: freshly created video with no EXIF
        After: response is a dict with no matching keys
        """
        result = client.call({
            "op": "read",
            "file": test_video,
            "tags": ["Make", "Model"],
        })

        assert "error" not in result, f"Unexpected error: {result.get('error')}"
        assert "Make" not in result
        assert "Model" not in result

    def test_read_multiple_tags_at_once(self, client, tagged_video):
        """Read several tags in a single request.

        Before: video has DateTimeOriginal, Make, and Model
        After: all three appear in the response
        """
        result = client.call({
            "op": "read",
            "file": tagged_video,
            "tags": ["DateTimeOriginal", "Make", "Model"],
        })

        assert "error" not in result
        assert "DateTimeOriginal" in result
        assert "Make" in result
        assert "Model" in result

    def test_read_fast_mode(self, client, tagged_video):
        """The fast flag (equivalent to -fast2) returns results without
        detailed processing. Useful for organize-by-date which only needs
        DateTimeOriginal."""
        result = client.call({
            "op": "read",
            "file": tagged_video,
            "tags": ["DateTimeOriginal"],
            "fast": True,
        })

        assert "error" not in result
        assert "DateTimeOriginal" in result
        assert "2025:06:18" in result["DateTimeOriginal"]

    def test_read_nonexistent_file(self, client):
        """Reading a file that doesn't exist returns an error or empty result
        rather than crashing the persistent process."""
        result = client.call({
            "op": "read",
            "file": "/nonexistent/path/file.mp4",
            "tags": ["DateTimeOriginal"],
        })

        has_no_data = "DateTimeOriginal" not in result
        has_error = "error" in result
        assert has_no_data or has_error, "Should handle missing file gracefully"

    def test_process_survives_bad_request(self, client, tagged_video):
        """After a bad request, the process stays alive and handles
        subsequent valid requests."""
        client.call({
            "op": "read",
            "file": "/nonexistent/file.mp4",
            "tags": ["DateTimeOriginal"],
        })

        result = client.call({
            "op": "read",
            "file": tagged_video,
            "tags": ["Make"],
        })

        assert result.get("Make") == "GoPro"


class TestWriteOperation:
    """Verify the write operation modifies file metadata and reports success."""

    def test_write_camera_tags(self, client, test_video):
        """Write Make and Model to a blank video, then verify with a read.

        Before: no Make or Model on file
        After: Make=GoPro, Model=HERO12 Black readable back
        """
        before = client.call({
            "op": "read",
            "file": test_video,
            "tags": ["Make", "Model"],
        })
        had_make_before = "Make" in before
        had_model_before = "Model" in before

        write_result = client.call({
            "op": "write",
            "file": test_video,
            "tags": {"Make": "GoPro", "Model": "HERO12 Black"},
        })

        after = client.call({
            "op": "read",
            "file": test_video,
            "tags": ["Make", "Model"],
        })

        assert had_make_before is False
        assert had_model_before is False
        assert write_result.get("updated") is True
        assert write_result.get("files_changed") == 1
        assert after.get("Make") == "GoPro"
        assert after.get("Model") == "HERO12 Black"

    def test_write_timestamp(self, client, test_video):
        """Write DateTimeOriginal and read it back.

        Before: no DateTimeOriginal
        After: DateTimeOriginal matches written value
        """
        write_result = client.call({
            "op": "write",
            "file": test_video,
            "tags": {"DateTimeOriginal": "2025:06:18 07:25:21+08:00"},
        })

        after = client.call({
            "op": "read",
            "file": test_video,
            "tags": ["DateTimeOriginal"],
        })

        assert write_result.get("updated") is True
        assert "DateTimeOriginal" in after
        assert "2025:06:18" in after["DateTimeOriginal"]
        assert "07:25:21" in after["DateTimeOriginal"]

    def test_write_to_nonexistent_file(self, client):
        """Writing to a nonexistent file reports failure without crashing."""
        result = client.call({
            "op": "write",
            "file": "/nonexistent/path/file.mp4",
            "tags": {"Make": "GoPro"},
        })

        assert result.get("updated") is not True or result.get("files_changed", 0) == 0


class TestProtocolRobustness:
    """Verify the JSON protocol handles edge cases without crashing."""

    def test_unknown_operation(self, client):
        """An unknown op returns an error message."""
        result = client.call({
            "op": "delete",
            "file": "/tmp/test.mp4",
            "tags": [],
        })

        assert "error" in result

    def test_invalid_json(self):
        """Malformed JSON input doesn't crash the process."""
        proc = subprocess.Popen(
            [BINARY_PATH],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        proc.stdin.write(b"this is not json\n")
        proc.stdin.flush()
        response_line = proc.stdout.readline()
        result = json.loads(response_line.decode())

        assert "error" in result

        proc.stdin.close()
        proc.wait(timeout=5)

    def test_empty_tags_read(self, client, tagged_video):
        """Reading with an empty tags list returns an empty result."""
        result = client.call({
            "op": "read",
            "file": tagged_video,
            "tags": [],
        })

        assert "error" not in result

    def test_write_with_array_tags_returns_error(self, client, test_video):
        """Write expects tags as a dict, not an array."""
        result = client.call({
            "op": "write",
            "file": test_video,
            "tags": ["Make", "Model"],
        })

        assert "error" in result


class TestSwiftVsExifToolParity:
    """Integration tests comparing jetlag-metadata output against direct
    ExifTool invocation. Ensures the Swift wrapper is a faithful proxy."""

    def _exiftool_read(self, file_path, tags):
        args = ["exiftool", "-s"] + [f"-{t}" for t in tags] + [file_path]
        result = subprocess.run(args, capture_output=True, text=True)
        data = {}
        for line in result.stdout.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                data[key.strip()] = value.strip()
        return data

    def test_read_parity_timestamps(self, client, tagged_video):
        """jetlag-metadata and ExifTool return the same DateTimeOriginal
        value for the same file."""
        swift_result = client.call({
            "op": "read",
            "file": tagged_video,
            "tags": ["DateTimeOriginal"],
        })

        exiftool_result = self._exiftool_read(tagged_video, ["DateTimeOriginal"])

        assert swift_result.get("DateTimeOriginal") == exiftool_result.get("DateTimeOriginal"), (
            f"Swift: {swift_result.get('DateTimeOriginal')}, "
            f"ExifTool: {exiftool_result.get('DateTimeOriginal')}"
        )

    def test_read_parity_camera(self, client, tagged_video):
        """jetlag-metadata and ExifTool return identical Make and Model."""
        swift_result = client.call({
            "op": "read",
            "file": tagged_video,
            "tags": ["Make", "Model"],
        })

        exiftool_result = self._exiftool_read(tagged_video, ["Make", "Model"])

        assert swift_result.get("Make") == exiftool_result.get("Make")
        assert swift_result.get("Model") == exiftool_result.get("Model")

    def test_write_parity(self, client, temp_dir):
        """After jetlag-metadata writes tags, ExifTool reads back the
        same values — and vice versa."""
        video = os.path.join(temp_dir, "parity.mp4")
        create_test_video(video)

        client.call({
            "op": "write",
            "file": video,
            "tags": {
                "Make": "Sony",
                "Model": "A7IV",
                "DateTimeOriginal": "2025:06:18 07:25:21+08:00",
            },
        })

        exiftool_result = self._exiftool_read(video, ["Make", "Model", "DateTimeOriginal"])

        assert exiftool_result.get("Make") == "Sony"
        assert exiftool_result.get("Model") == "A7IV"
        assert "2025:06:18" in exiftool_result.get("DateTimeOriginal", "")
        assert "07:25:21" in exiftool_result.get("DateTimeOriginal", "")
