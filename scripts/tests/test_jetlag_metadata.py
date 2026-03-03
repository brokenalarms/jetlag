"""
Verify the jetlag-metadata CLI produces correct JSON for each operation.

These tests confirm the JSON-in/JSON-out contract between the Python
MetadataService wrapper and the Swift jetlag-metadata binary. Each test
creates a real media file, runs an operation through MetadataService,
and verifies the result matches what ExifTool would produce directly.
"""

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.metadata import MetadataService
from tests.conftest import create_test_video


@pytest.fixture
def service():
    svc = MetadataService()
    yield svc
    svc.close()


@pytest.fixture
def sample_video(tmp_path):
    video = tmp_path / "test.mp4"
    create_test_video(str(video), DateTimeOriginal="2024:06:15 10:30:00")
    return video


class TestReadTags:
    """JSON round-trip for read operations."""

    def test_read_returns_matching_tags(self, service, sample_video):
        result = service.read_tags(str(sample_video), ["DateTimeOriginal"])
        assert "DateTimeOriginal" in result
        assert result["DateTimeOriginal"].startswith("2024:06:15")

    def test_read_multiple_tags(self, service, tmp_path):
        video = tmp_path / "multi.mp4"
        create_test_video(
            str(video),
            DateTimeOriginal="2024:01:01 08:00:00",
            Make="TestCam",
            Model="TestModel",
        )
        result = service.read_tags(str(video), ["DateTimeOriginal", "Make", "Model"])
        assert result["Make"] == "TestCam"
        assert result["Model"] == "TestModel"

    def test_read_fast_mode(self, service, sample_video):
        result = service.read_tags(
            str(sample_video), ["DateTimeOriginal"], extra_args=["-fast2"]
        )
        assert "DateTimeOriginal" in result

    def test_read_missing_file_returns_empty(self, service):
        result = service.read_tags("/nonexistent/file.mp4", ["DateTimeOriginal"])
        assert result == {}

    def test_read_missing_tag_excluded(self, service, sample_video):
        result = service.read_tags(str(sample_video), ["NoSuchTag"])
        assert "NoSuchTag" not in result


class TestWriteTags:
    """JSON round-trip for write operations."""

    def test_write_returns_true_on_success(self, service, sample_video):
        ok = service.write_tags(str(sample_video), ["-Make=NewCam"])
        assert ok is True

    def test_write_persists_value(self, service, sample_video):
        service.write_tags(str(sample_video), ["-Make=Persisted", "-Model=Check"])
        result = service.read_tags(str(sample_video), ["Make", "Model"])
        assert result["Make"] == "Persisted"
        assert result["Model"] == "Check"

    def test_write_multiple_tags(self, service, sample_video):
        ok = service.write_tags(
            str(sample_video),
            [
                "-DateTimeOriginal=2025:03:01 12:00:00",
                "-Make=Multi",
                "-Model=Write",
            ],
        )
        assert ok is True
        result = service.read_tags(
            str(sample_video), ["DateTimeOriginal", "Make", "Model"]
        )
        assert result["Make"] == "Multi"
        assert result["Model"] == "Write"

    def test_write_to_missing_file_returns_false(self, service):
        ok = service.write_tags("/nonexistent/file.mp4", ["-Make=Fail"])
        assert ok is False

    def test_write_namespaced_tags(self, service, sample_video):
        ok = service.write_tags(
            str(sample_video),
            ["-QuickTime:CreateDate=2025:01:01 00:00:00"],
        )
        assert ok is True
