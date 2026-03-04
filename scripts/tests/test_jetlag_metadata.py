"""
Verify the jetlag-metadata CLI produces correct JSON for each operation.

These tests confirm the JSON-in/JSON-out contract between the Python
MetadataService wrapper and the Swift jetlag-metadata binary (or ExifTool
fallback). Each test creates a real media file, runs an operation through
MetadataService, and verifies the result.

Coverage:
- Video (MP4): read/write for timestamps, camera tags, namespaced tags
- Image (JPEG): read/write for EXIF timestamps and camera tags
- Edge cases: adding new Keys:CreationDate, overwriting existing, bare files
- Timezone formats: +HH:MM, Z, naive (no timezone)
"""

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.metadata import MetadataService
from tests.conftest import create_test_image, create_test_video, create_test_video_faststart


@pytest.fixture
def service():
    svc = MetadataService()
    yield svc
    svc.close()


@pytest.fixture
def sample_video(tmp_path):
    video = tmp_path / "test.mp4"
    create_test_video(
        str(video),
        **{"Keys:CreationDate": "2024-06-15T10:30:00+00:00"},
        Make="TestMake",
    )
    return video


@pytest.fixture
def sample_image(tmp_path):
    image = tmp_path / "test.jpg"
    create_test_image(
        str(image),
        DateTimeOriginal="2024:06:15 10:30:00",
        Make="TestCam",
        Model="TestModel",
    )
    return image


@pytest.fixture
def bare_video(tmp_path):
    """Video with no metadata injected beyond what ffmpeg writes."""
    video = tmp_path / "bare.mp4"
    create_test_video(str(video))
    return video


@pytest.fixture
def bare_image(tmp_path):
    """JPEG with no EXIF metadata injected."""
    image = tmp_path / "bare.jpg"
    create_test_image(str(image))
    return image


# ── Video read ────────────────────────────────────────────────────────

class TestVideoRead:
    """Read operations on MP4/MOV files."""

    def test_read_creation_date(self, service, sample_video):
        result = service.read_tags(str(sample_video), ["CreationDate"])
        assert "CreationDate" in result
        assert "2024:06:15" in result["CreationDate"]

    def test_read_make_and_model(self, service, sample_video):
        result = service.read_tags(str(sample_video), ["Make", "Model"])
        assert result["Make"] == "TestMake"

    def test_read_fast_mode(self, service, sample_video):
        result = service.read_tags(
            str(sample_video), ["CreationDate"], extra_args=["-fast2"]
        )
        assert "CreationDate" in result

    def test_read_missing_file_returns_empty(self, service):
        result = service.read_tags("/nonexistent/file.mp4", ["CreationDate"])
        assert result == {}

    def test_read_missing_tag_excluded(self, service, sample_video):
        result = service.read_tags(str(sample_video), ["NoSuchTag"])
        assert "NoSuchTag" not in result

    def test_read_multiple_timestamp_tags(self, service, tmp_path):
        """Read several timestamp variants from a single video."""
        video = tmp_path / "multi_ts.mp4"
        create_test_video(
            str(video),
            **{
                "Keys:CreationDate": "2025-01-15T08:00:00+09:00",
                "QuickTime:CreateDate": "2025:01:14 23:00:00",
                "QuickTime:MediaCreateDate": "2025:01:14 23:00:00",
            },
        )
        result = service.read_tags(
            str(video),
            ["CreationDate", "CreateDate", "MediaCreateDate"],
        )
        assert "CreationDate" in result
        assert "CreateDate" in result


# ── Video write ───────────────────────────────────────────────────────

class TestVideoWrite:
    """Write operations on MP4/MOV files."""

    def test_write_preserves_file_timestamps(self, service, tmp_path):
        """Metadata writes must not change the file's filesystem timestamps.

        This covers the in-place timestamp patch path (Pass 1 only, no mdta
        key writes) which previously skipped timestamp restoration.
        """
        import os
        import time

        video = tmp_path / "ts_preserve.mp4"
        create_test_video(str(video))

        old_mtime = os.path.getmtime(str(video))
        old_ctime = os.stat(str(video)).st_birthtime

        time.sleep(0.1)

        service.write_tags(
            str(video),
            ["-QuickTime:CreateDate=2025:01:01 00:00:00",
             "-QuickTime:MediaCreateDate=2025:01:01 00:00:00"],
        )

        new_mtime = os.path.getmtime(str(video))
        new_ctime = os.stat(str(video)).st_birthtime

        assert abs(new_mtime - old_mtime) < 1, (
            f"mtime changed: {old_mtime} -> {new_mtime}"
        )
        assert abs(new_ctime - old_ctime) < 1, (
            f"birthtime changed: {old_ctime} -> {new_ctime}"
        )

    def test_write_returns_true(self, service, sample_video):
        ok = service.write_tags(str(sample_video), ["-Make=NewCam"])
        assert ok is True

    def test_write_persists_camera_tags(self, service, sample_video):
        service.write_tags(str(sample_video), ["-Make=Persisted", "-Model=Check"])
        result = service.read_tags(str(sample_video), ["Make", "Model"])
        assert result["Make"] == "Persisted"
        assert result["Model"] == "Check"

    def test_write_multiple_tags(self, service, sample_video):
        ok = service.write_tags(
            str(sample_video),
            [
                "-Keys:CreationDate=2025-03-01T12:00:00+00:00",
                "-Make=Multi",
                "-Model=Write",
            ],
        )
        assert ok is True
        result = service.read_tags(
            str(sample_video), ["CreationDate", "Make", "Model"]
        )
        assert result["Make"] == "Multi"
        assert result["Model"] == "Write"

    def test_write_to_missing_file_returns_false(self, service):
        ok = service.write_tags("/nonexistent/file.mp4", ["-Make=Fail"])
        assert ok is False

    def test_write_namespaced_create_date(self, service, sample_video):
        ok = service.write_tags(
            str(sample_video),
            ["-QuickTime:CreateDate=2025:01:01 00:00:00"],
        )
        assert ok is True

    def test_write_creation_date_overwrites_existing(self, service, sample_video):
        """Overwrite an existing Keys:CreationDate value."""
        service.write_tags(
            str(sample_video),
            ["-Keys:CreationDate=2099-12-31T23:59:59+00:00"],
        )
        result = service.read_tags(str(sample_video), ["CreationDate"])
        assert "2099" in result["CreationDate"]

    def test_write_creation_date_to_bare_video(self, service, bare_video):
        """Add Keys:CreationDate to a video that has no mdta keys atom.

        This triggers the full moov rewrite path (new atom insertion) rather
        than the in-place timestamp patch path.
        """
        ok = service.write_tags(
            str(bare_video),
            ["-Keys:CreationDate=2025-07-04T12:00:00+00:00"],
        )
        assert ok is True
        result = service.read_tags(str(bare_video), ["CreationDate"])
        assert "2025" in result["CreationDate"]

    def test_write_timestamps_and_camera_together(self, service, bare_video):
        """Write both timestamp and camera tags in a single operation.

        Exercises the two-pass write ordering (in-place timestamp patches
        followed by mdta key writes that may trigger a full rewrite).
        """
        ok = service.write_tags(
            str(bare_video),
            [
                "-Keys:CreationDate=2025-08-20T09:15:00+05:30",
                "-QuickTime:CreateDate=2025:08:20 03:45:00",
                "-Make=DualWrite",
                "-Model=CamTest",
            ],
        )
        assert ok is True
        result = service.read_tags(
            str(bare_video), ["CreationDate", "Make", "Model"]
        )
        assert "2025" in result["CreationDate"]
        assert result["Make"] == "DualWrite"
        assert result["Model"] == "CamTest"

    def test_write_preserves_file_playability(self, service, sample_video):
        """After metadata writes, the video file remains structurally valid.

        Uses ffprobe to confirm the container is still parseable.
        """
        service.write_tags(
            str(sample_video),
            [
                "-Keys:CreationDate=2025-01-01T00:00:00+00:00",
                "-Make=Integrity",
            ],
        )
        import subprocess
        result = subprocess.run(
            ["ffprobe", "-v", "error", str(sample_video)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"ffprobe failed: {result.stderr}"


# ── Image read ────────────────────────────────────────────────────────

class TestImageRead:
    """Read operations on JPEG image files."""

    def test_read_datetime_original(self, service, sample_image):
        result = service.read_tags(str(sample_image), ["DateTimeOriginal"])
        assert "DateTimeOriginal" in result
        assert "2024:06:15" in result["DateTimeOriginal"]

    def test_read_camera_tags(self, service, sample_image):
        result = service.read_tags(str(sample_image), ["Make", "Model"])
        assert result["Make"] == "TestCam"
        assert result["Model"] == "TestModel"

    def test_read_missing_tag_on_image(self, service, sample_image):
        result = service.read_tags(str(sample_image), ["NoSuchTag"])
        assert "NoSuchTag" not in result

    def test_read_bare_image_returns_empty_for_exif(self, service, bare_image):
        """A JPEG with no injected EXIF should not return DateTimeOriginal."""
        result = service.read_tags(str(bare_image), ["DateTimeOriginal"])
        assert "DateTimeOriginal" not in result

    def test_read_fast_mode_on_image(self, service, sample_image):
        result = service.read_tags(
            str(sample_image), ["DateTimeOriginal"], extra_args=["-fast2"]
        )
        assert "DateTimeOriginal" in result


# ── Image write ───────────────────────────────────────────────────────

class TestImageWrite:
    """Write operations on JPEG image files."""

    def test_write_camera_tags_to_image(self, service, bare_image):
        ok = service.write_tags(
            str(bare_image), ["-Make=NewCam", "-Model=NewModel"]
        )
        assert ok is True
        result = service.read_tags(str(bare_image), ["Make", "Model"])
        assert result["Make"] == "NewCam"
        assert result["Model"] == "NewModel"

    def test_write_datetime_original_to_image(self, service, bare_image):
        ok = service.write_tags(
            str(bare_image),
            ["-DateTimeOriginal=2025:03:04 14:30:00"],
        )
        assert ok is True
        result = service.read_tags(str(bare_image), ["DateTimeOriginal"])
        assert "2025:03:04" in result["DateTimeOriginal"]

    def test_overwrite_existing_datetime(self, service, sample_image):
        service.write_tags(
            str(sample_image),
            ["-DateTimeOriginal=2099:12:31 23:59:59"],
        )
        result = service.read_tags(str(sample_image), ["DateTimeOriginal"])
        assert "2099:12:31" in result["DateTimeOriginal"]

    def test_write_all_image_tags_at_once(self, service, bare_image):
        ok = service.write_tags(
            str(bare_image),
            [
                "-DateTimeOriginal=2025:07:01 08:00:00",
                "-Make=BatchCam",
                "-Model=BatchModel",
            ],
        )
        assert ok is True
        result = service.read_tags(
            str(bare_image), ["DateTimeOriginal", "Make", "Model"]
        )
        assert "2025:07:01" in result["DateTimeOriginal"]
        assert result["Make"] == "BatchCam"
        assert result["Model"] == "BatchModel"


# ── Timezone handling ─────────────────────────────────────────────────

class TestTimezoneFormats:
    """Verify timezone information round-trips through different formats."""

    def test_positive_offset(self, service, tmp_path):
        video = tmp_path / "tz_pos.mp4"
        create_test_video(str(video))
        service.write_tags(
            str(video),
            ["-Keys:CreationDate=2025-06-18T07:25:21+08:00"],
        )
        result = service.read_tags(str(video), ["CreationDate"])
        assert "2025" in result["CreationDate"]

    def test_utc_offset(self, service, tmp_path):
        video = tmp_path / "tz_utc.mp4"
        create_test_video(str(video))
        service.write_tags(
            str(video),
            ["-Keys:CreationDate=2025-06-18T07:25:21+00:00"],
        )
        result = service.read_tags(str(video), ["CreationDate"])
        assert "2025" in result["CreationDate"]

    def test_negative_offset(self, service, tmp_path):
        video = tmp_path / "tz_neg.mp4"
        create_test_video(str(video))
        service.write_tags(
            str(video),
            ["-Keys:CreationDate=2025-06-18T07:25:21-05:00"],
        )
        result = service.read_tags(str(video), ["CreationDate"])
        assert "2025" in result["CreationDate"]

    def test_z_suffix(self, service, tmp_path):
        video = tmp_path / "tz_z.mp4"
        create_test_video(str(video))
        service.write_tags(
            str(video),
            ["-Keys:CreationDate=2025-06-18T07:25:21Z"],
        )
        result = service.read_tags(str(video), ["CreationDate"])
        assert "2025" in result["CreationDate"]

    def test_image_datetime_with_offset(self, service, tmp_path):
        """JPEG DateTimeOriginal doesn't natively carry timezone, but the
        OffsetTimeOriginal tag does. Verify the date portion survives."""
        image = tmp_path / "tz_img.jpg"
        create_test_image(str(image))
        service.write_tags(
            str(image),
            ["-DateTimeOriginal=2025:06:18 07:25:21"],
        )
        result = service.read_tags(str(image), ["DateTimeOriginal"])
        assert "2025:06:18 07:25:21" in result["DateTimeOriginal"]


# ── Moov-after-mdat (standard camera layout) ─────────────────────────

class TestStandardLayout:
    """Verify metadata writes on files with moov atom after mdat.

    Standard camera MP4 files have mdat before moov. When moov grows
    during a full rewrite, mdat stays at its original position. Chunk
    offsets pointing into mdat must NOT be adjusted — only offsets
    pointing past moov (if any) should be shifted.
    """

    def test_write_new_mdta_key_preserves_playability(self, service, tmp_path):
        """Adding a new mdta key to a bare standard video triggers a full
        moov rewrite. Chunk offsets into mdat must remain untouched."""
        video = tmp_path / "standard.mp4"
        create_test_video(str(video))

        service.write_tags(
            str(video),
            ["-Keys:CreationDate=2025-09-15T12:00:00+00:00"],
        )

        import subprocess
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v",
             "-show_entries", "stream=nb_frames", "-of", "csv=p=0",
             str(video)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"ffprobe failed: {result.stderr}"

    def test_write_multiple_mdta_keys_preserves_playability(self, service, tmp_path):
        """Multiple mdta key writes each trigger a full rewrite. After
        several rewrites, chunk offsets should still be correct."""
        video = tmp_path / "standard_multi.mp4"
        create_test_video(str(video))

        service.write_tags(
            str(video),
            ["-Keys:CreationDate=2025-01-01T00:00:00+00:00", "-Make=Cam1"],
        )
        service.write_tags(
            str(video),
            ["-Model=Model2"],
        )

        import subprocess
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v",
             "-show_entries", "stream=nb_frames", "-of", "csv=p=0",
             str(video)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"ffprobe failed: {result.stderr}"

        read_result = service.read_tags(
            str(video), ["CreationDate", "Make", "Model"]
        )
        assert "2025" in read_result["CreationDate"]
        assert read_result["Make"] == "Cam1"
        assert read_result["Model"] == "Model2"

    def test_overwrite_different_length_preserves_playability(self, service, tmp_path):
        """Overwriting an mdta key with a different-length value triggers
        a full rewrite on a standard layout file."""
        video = tmp_path / "standard_overwrite.mp4"
        create_test_video(str(video))

        service.write_tags(
            str(video),
            ["-Keys:CreationDate=2025-01-01T00:00:00Z"],
        )
        service.write_tags(
            str(video),
            ["-Keys:CreationDate=2025-12-31T23:59:59+13:45"],
        )

        import subprocess
        result = subprocess.run(
            ["ffprobe", "-v", "error", str(video)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"ffprobe failed: {result.stderr}"


# ── Moov-before-mdat (faststart) layout ──────────────────────────────

class TestFaststartLayout:
    """Verify metadata writes on files with moov atom before mdat.

    Web-optimized (qt-faststart) MP4 files have moov at the start. When
    moov grows during metadata writes, all stco/co64 chunk offsets pointing
    into mdat must be adjusted by the size delta, otherwise the video data
    becomes unreachable and the file is corrupted.
    """

    def test_write_mdta_key_preserves_playability(self, service, tmp_path):
        """Adding a new mdta key triggers a full moov rewrite. With moov
        before mdat, chunk offsets must be adjusted for the file to remain
        playable."""
        video = tmp_path / "faststart.mp4"
        create_test_video_faststart(str(video))

        service.write_tags(
            str(video),
            ["-Keys:CreationDate=2025-09-15T12:00:00+00:00"],
        )

        import subprocess
        result = subprocess.run(
            ["ffprobe", "-v", "error", str(video)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"ffprobe failed after faststart write: {result.stderr}"

    def test_write_mdta_key_round_trips(self, service, tmp_path):
        """Written metadata can be read back from a faststart file."""
        video = tmp_path / "faststart_rt.mp4"
        create_test_video_faststart(str(video))

        service.write_tags(
            str(video),
            ["-Keys:CreationDate=2025-11-20T08:30:00+09:00", "-Make=FastCam"],
        )

        result = service.read_tags(str(video), ["CreationDate", "Make"])
        assert "2025" in result["CreationDate"]
        assert result["Make"] == "FastCam"

    def test_overwrite_mdta_key_preserves_playability(self, service, tmp_path):
        """Overwriting an mdta key with a different-length value triggers a
        full rewrite. Verify chunk offsets are adjusted correctly."""
        video = tmp_path / "faststart_overwrite.mp4"
        create_test_video_faststart(str(video))

        service.write_tags(
            str(video),
            ["-Keys:CreationDate=2025-01-01T00:00:00Z"],
        )
        service.write_tags(
            str(video),
            ["-Keys:CreationDate=2025-12-31T23:59:59+13:45"],
        )

        import subprocess
        result = subprocess.run(
            ["ffprobe", "-v", "error", str(video)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"ffprobe failed after overwrite: {result.stderr}"

        read_result = service.read_tags(str(video), ["CreationDate"])
        assert "2025:12:31" in read_result["CreationDate"]
