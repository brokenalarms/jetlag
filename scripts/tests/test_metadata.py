"""
Tests for MetadataService — the Python wrapper around the jetlag-metadata CLI.

Validates that the service correctly translates the ExifTool-compatible
read_tags/write_tags API into the JSON protocol expected by jetlag-metadata,
and correctly interprets responses.
"""

import json
import threading
from unittest.mock import MagicMock, patch

import pytest

from lib.metadata import MetadataService


def make_fake_process(responses: list[dict]):
    """Create a mock subprocess that returns pre-canned JSON responses."""
    proc = MagicMock()
    proc.poll.return_value = None
    proc.stdin = MagicMock()
    response_lines = [json.dumps(r).encode() + b"\n" for r in responses]
    proc.stdout = MagicMock()
    proc.stdout.readline = MagicMock(side_effect=response_lines)
    return proc


class TestReadTags:
    """Verifies read_tags sends correct JSON and parses the response dict."""

    def test_basic_read(self):
        svc = MetadataService()
        response = {"DateTimeOriginal": "2024:01:15 10:30:45", "Make": "GoPro"}
        svc._process = make_fake_process([response])

        result = svc.read_tags("/photo.jpg", ["DateTimeOriginal", "Make"])

        sent = json.loads(svc._process.stdin.write.call_args[0][0].decode())
        assert sent["op"] == "read"
        assert sent["file"] == "/photo.jpg"
        assert sent["tags"] == ["DateTimeOriginal", "Make"]
        assert "fast" not in sent
        assert result == {"DateTimeOriginal": "2024:01:15 10:30:45", "Make": "GoPro"}

    def test_read_with_fast2(self):
        svc = MetadataService()
        svc._process = make_fake_process([{"DateTimeOriginal": "2024:01:15"}])

        svc.read_tags("/photo.jpg", ["DateTimeOriginal"], extra_args=["-fast2"])

        sent = json.loads(svc._process.stdin.write.call_args[0][0].decode())
        assert sent["fast"] is True

    def test_read_ignores_non_fast_extra_args(self):
        svc = MetadataService()
        svc._process = make_fake_process([{"Make": "Canon"}])

        svc.read_tags("/photo.jpg", ["Make"], extra_args=["-s"])

        sent = json.loads(svc._process.stdin.write.call_args[0][0].decode())
        assert "fast" not in sent


class TestWriteTags:
    """Verifies write_tags parses ExifTool-style tag args into JSON dict."""

    def test_basic_write(self):
        svc = MetadataService()
        svc._process = make_fake_process([{"updated": True, "files_changed": 1}])

        result = svc.write_tags("/photo.jpg", ["-Make=GoPro", "-Model=Hero12"])

        sent = json.loads(svc._process.stdin.write.call_args[0][0].decode())
        assert sent["op"] == "write"
        assert sent["file"] == "/photo.jpg"
        assert sent["tags"] == {"Make": "GoPro", "Model": "Hero12"}
        assert result is True

    def test_write_returns_false_when_not_updated(self):
        svc = MetadataService()
        svc._process = make_fake_process([{"updated": False, "files_changed": 0}])

        result = svc.write_tags("/photo.jpg", ["-Make=GoPro"])
        assert result is False

    def test_write_handles_group_prefixed_tags(self):
        svc = MetadataService()
        svc._process = make_fake_process([{"updated": True, "files_changed": 1}])

        svc.write_tags("/video.mov", ["-Keys:CreationDate=2024:01:15"])

        sent = json.loads(svc._process.stdin.write.call_args[0][0].decode())
        assert sent["tags"] == {"Keys:CreationDate": "2024:01:15"}

    def test_write_handles_value_with_equals(self):
        """Tag values containing '=' should not be split incorrectly."""
        svc = MetadataService()
        svc._process = make_fake_process([{"updated": True, "files_changed": 1}])

        svc.write_tags("/photo.jpg", ["-Comment=key=value"])

        sent = json.loads(svc._process.stdin.write.call_args[0][0].decode())
        assert sent["tags"] == {"Comment": "key=value"}


class TestErrorHandling:
    """Verifies error responses from the CLI are raised as exceptions."""

    def test_error_response_raises(self):
        svc = MetadataService()
        svc._process = make_fake_process([{"error": "Unknown operation: foo"}])

        with pytest.raises(RuntimeError, match="Unknown operation: foo"):
            svc.read_tags("/photo.jpg", ["Make"])

    def test_process_not_found(self):
        svc = MetadataService()
        with patch("lib.metadata.subprocess.Popen", side_effect=FileNotFoundError):
            with pytest.raises(FileNotFoundError):
                svc.read_tags("/photo.jpg", ["Make"])

    def test_unavailable_flag_persists(self):
        """After FileNotFoundError, subsequent calls fail immediately."""
        svc = MetadataService()
        with patch("lib.metadata.subprocess.Popen", side_effect=FileNotFoundError):
            with pytest.raises(FileNotFoundError):
                svc.read_tags("/photo.jpg", ["Make"])

        with pytest.raises(FileNotFoundError, match="not available"):
            svc.read_tags("/photo.jpg", ["Make"])


class TestLifecycle:
    """Verifies process startup and shutdown behavior."""

    def test_close_shuts_down_process(self):
        svc = MetadataService()
        proc = MagicMock()
        proc.poll.return_value = None
        proc.stdin = MagicMock()
        proc.wait.return_value = 0
        svc._process = proc

        svc.close()

        proc.stdin.close.assert_called_once()
        proc.wait.assert_called_once()
        assert svc._process is None

    def test_close_kills_on_timeout(self):
        import subprocess as sp

        svc = MetadataService()
        proc = MagicMock()
        proc.poll.return_value = None
        proc.stdin = MagicMock()
        proc.wait.side_effect = [sp.TimeoutExpired("jetlag-metadata", 5), 0]
        svc._process = proc

        svc.close()

        proc.kill.assert_called_once()
        assert svc._process is None
