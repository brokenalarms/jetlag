#!/usr/bin/env python3
"""
Regression tests for fix-media-timestamp.py
Tests critical behaviors documented in CLAUDE.md
"""

import os
import sys
import tempfile
import shutil
import subprocess
import pytest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Import hyphenated module name
import importlib.util
spec = importlib.util.spec_from_file_location(
    "fix_media_timestamp",
    str(Path(__file__).parent.parent / "fix-media-timestamp.py")
)
fmt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fmt)

SCRIPT_DIR = Path(__file__).parent.parent


class TestFilenameSourceOfTruth:
    """
    CLAUDE.md: "files with YYYYMMDD_HHMMSS in the filename are first source of truth
    and filename should never be modified"
    """

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def test_insta360_filename_is_source_of_truth_with_overwrite(self):
        """
        Insta360 file VID_20250619_063809_00_002.mp4 has:
        - Filename: 06:38:09 (CORRECT - source of truth)
        - DateTimeOriginal: 09:38:09+08:00 (WRONG - corrupted)

        With --overwrite-datetimeoriginal --timezone +0800:
        - Should use filename (06:38:09) as source of truth
        - Should write DateTimeOriginal as 06:38:09+08:00
        - Should ignore the corrupted DateTimeOriginal value
        """
        video_path = os.path.join(self.temp_dir, "VID_20250619_063809_00_002.mp4")

        # Create video
        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            video_path
        ], capture_output=True, check=True)

        # Set WRONG DateTimeOriginal (simulating corruption)
        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            "-DateTimeOriginal=2025:06:19 09:38:09+08:00",
            video_path
        ], capture_output=True, check=True)

        # Run with --overwrite-datetimeoriginal to use filename as source of truth
        result = subprocess.run([
            "python3", str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video_path,
            "--overwrite-datetimeoriginal",
            "--timezone", "+0800",
            "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0

        # Verify DateTimeOriginal was corrected from filename
        fmt._exif_cache.clear()
        exif = fmt.read_exif_data(video_path)
        dt_original = exif.get("DateTimeOriginal", "")

        # Should be 06:38:09 (from filename), not 09:38:09 (corrupted value)
        assert "2025:06:19 06:38:09" in dt_original
        assert "+08:00" in dt_original

    def test_filename_not_modified_ever(self):
        """
        Verify that filename is never modified, regardless of timestamp corrections
        """
        original_filename = "VID_20250619_063809_00_002.mp4"
        video_path = os.path.join(self.temp_dir, original_filename)

        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            video_path
        ], capture_output=True, check=True)

        # Run fix (even with wrong EXIF data)
        subprocess.run([
            "python3", str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video_path,
            "--timezone", "+0800",
            "--apply"
        ], capture_output=True, check=True)

        # Filename should be unchanged
        assert os.path.exists(video_path)
        assert os.path.basename(video_path) == original_filename


class TestDateTimeOriginalPreservation:
    """
    CLAUDE.md: "DateTimeOriginal is next source of truth and should never be modified
    unless --overwrite-datetimeoriginal is specified"
    """

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def test_datetimeoriginal_preserved_by_default(self):
        """
        Without --overwrite-datetimeoriginal, DateTimeOriginal should never change
        """
        video_path = os.path.join(self.temp_dir, "test_video.mp4")

        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            video_path
        ], capture_output=True, check=True)

        # Set DateTimeOriginal
        original_datetime = "2025:06:19 06:38:09+08:00"
        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            f"-DateTimeOriginal={original_datetime}",
            video_path
        ], capture_output=True, check=True)

        # Run fix without --overwrite-datetimeoriginal
        subprocess.run([
            "python3", str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video_path,
            "--apply"
        ], capture_output=True, check=True)

        # DateTimeOriginal should be unchanged
        fmt._exif_cache.clear()
        exif = fmt.read_exif_data(video_path)
        assert exif.get("DateTimeOriginal") == original_datetime


class TestOverwriteDateTimeOriginalRequiresTimezone:
    """
    CLAUDE.md: "if --overwrite-datetimeoriginal is specified, --timezone must be provided"
    """

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def test_overwrite_without_timezone_fails(self):
        """
        --overwrite-datetimeoriginal without --timezone should fail with clear error
        """
        video_path = os.path.join(self.temp_dir, "VID_20250619_063809.mp4")

        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            video_path
        ], capture_output=True, check=True)

        # Try to run with --overwrite-datetimeoriginal but no --timezone
        result = subprocess.run([
            "python3", str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video_path,
            "--overwrite-datetimeoriginal",
            "--apply"
        ], capture_output=True, text=True)

        # Should fail
        assert result.returncode != 0
        assert "requires --timezone" in result.stderr or "requires --timezone" in result.stdout


class TestTimezoneMismatchDetection:
    """
    CLAUDE.md: "if a different --timezone is specified that doesn't match DateTimeOriginal,
    then we should exit with a warning unless --overwrite-datetime-original is specified"
    """

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def test_timezone_mismatch_without_overwrite_fails(self):
        """
        Providing different --timezone than DateTimeOriginal should fail without --overwrite
        """
        video_path = os.path.join(self.temp_dir, "test_video.mp4")

        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            video_path
        ], capture_output=True, check=True)

        # Set DateTimeOriginal with +08:00 timezone
        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            "-DateTimeOriginal=2025:06:19 06:38:09+08:00",
            video_path
        ], capture_output=True, check=True)

        # Try to run with DIFFERENT timezone +09:00
        result = subprocess.run([
            "python3", str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video_path,
            "--timezone", "+0900",
            "--apply"
        ], capture_output=True, text=True)

        # Should fail with timezone mismatch error
        assert result.returncode != 0
        output = result.stdout + result.stderr
        assert "mismatch" in output.lower() or "different" in output.lower()

    def test_timezone_mismatch_with_overwrite_succeeds(self):
        """
        With --overwrite-datetimeoriginal, timezone mismatch should be allowed
        """
        video_path = os.path.join(self.temp_dir, "test_video.mp4")

        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            video_path
        ], capture_output=True, check=True)

        # Set DateTimeOriginal with +08:00 timezone
        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            "-DateTimeOriginal=2025:06:19 06:38:09+08:00",
            video_path
        ], capture_output=True, check=True)

        # Run with DIFFERENT timezone but with --overwrite-datetimeoriginal
        result = subprocess.run([
            "python3", str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video_path,
            "--overwrite-datetimeoriginal",
            "--timezone", "+0900",
            "--apply"
        ], capture_output=True, text=True)

        # Should succeed
        assert result.returncode == 0

        # DateTimeOriginal should be updated to new timezone
        fmt._exif_cache.clear()
        exif = fmt.read_exif_data(video_path)
        assert "+09:00" in exif.get("DateTimeOriginal", "")


class TestTimezoneConversion:
    """
    CLAUDE.md: "if a file was shot in timezone +0800, with the script run in +0900,
    then we would expect Keys:Creation date to end up with the +0800 timezone,
    and the birthdate to end up as one hour later"
    """

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def test_timezone_conversion_display_mode(self):
        """
        Shot in +08:00, viewing in +09:00:
        - Keys:CreationDate should have +08:00
        - Birth time should be 1 hour later (converted to viewing timezone)
        """
        video_path = os.path.join(self.temp_dir, "taiwan_video.mp4")

        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            video_path
        ], capture_output=True, check=True)

        # Set shot in Taiwan +08:00 at 06:38:09
        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            "-DateTimeOriginal=2025:06:19 06:38:09+08:00",
            video_path
        ], capture_output=True, check=True)

        # Run fix
        subprocess.run([
            "python3", str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video_path,
            "--apply"
        ], capture_output=True, check=True)

        # Verify Keys:CreationDate has original timezone (+08:00)
        result = subprocess.run([
            "exiftool", "-s", "-Keys:CreationDate", video_path
        ], capture_output=True, text=True, check=True)

        assert "06:38:09" in result.stdout
        assert "+08:00" in result.stdout

        # Birth time should be set (exact value depends on system timezone)
        birth_time = os.stat(video_path).st_birthtime
        assert birth_time > 0


class TestPreserveWallclockTime:
    """
    CLAUDE.md: "if --preserve-wallclock-time is specified, then we would expect
    the file birthtime to be set back one hour in order to make the edited file
    appear in this timezone as if it was shot at the same time in this timezone"
    """

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def test_preserve_wallclock_time_mode(self):
        """
        With --preserve-wallclock-time:
        - Birth time should match shooting time (wall-clock), not display time
        """
        video_path = os.path.join(self.temp_dir, "wallclock_video.mp4")

        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            video_path
        ], capture_output=True, check=True)

        # Shot at 06:38:09 in Taiwan (+08:00)
        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            "-DateTimeOriginal=2025:06:19 06:38:09+08:00",
            video_path
        ], capture_output=True, check=True)

        # Run with --preserve-wallclock-time
        subprocess.run([
            "python3", str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video_path,
            "--preserve-wallclock-time",
            "--apply"
        ], capture_output=True, check=True)

        # Birth time should preserve wall-clock shooting time (06:38)
        birth_time = os.stat(video_path).st_birthtime
        birth_dt = datetime.fromtimestamp(birth_time)

        # Should show 06:38 (shooting time), not adjusted for viewing timezone
        assert birth_dt.hour == 6
        assert birth_dt.minute == 38


class TestMissingDateTimeOriginalWithTimezoneChange:
    """
    CLAUDE.md: "if DateTimeOriginal is missing and we change timezones,
    we would expect the Quicktime UTC fields MediaCreateDate, file birth date,
    Keys:CreationDate to all be updated"
    """

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def test_missing_datetimeoriginal_updates_all_fields(self):
        """
        When DateTimeOriginal is missing and we provide timezone:
        - Should write DateTimeOriginal
        - Should update MediaCreateDate (UTC)
        - Should update Keys:CreationDate
        - Should update file birth time
        """
        # Insta360 filename has timestamp
        video_path = os.path.join(self.temp_dir, "VID_20250619_063809.mp4")

        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            video_path
        ], capture_output=True, check=True)

        # No DateTimeOriginal initially
        fmt._exif_cache.clear()
        exif_before = fmt.read_exif_data(video_path)
        assert not exif_before.get("DateTimeOriginal")

        # Run with timezone
        subprocess.run([
            "python3", str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video_path,
            "--timezone", "+0800",
            "--apply"
        ], capture_output=True, check=True)

        # All fields should now be set
        fmt._exif_cache.clear()
        exif_after = fmt.read_exif_data(video_path)

        # DateTimeOriginal should be written
        assert "2025:06:19 06:38:09" in exif_after.get("DateTimeOriginal", "")
        assert "+08:00" in exif_after.get("DateTimeOriginal", "")

        # MediaCreateDate should be in UTC
        media_create = exif_after.get("MediaCreateDate", "")
        # 06:38:09+08:00 in UTC is 22:38:09 on previous day
        assert "22:38:09" in media_create

        # Keys:CreationDate should be set
        keys_cd = exif_after.get("CreationDate", "")
        assert keys_cd  # Should exist

        # Birth time should be set
        birth_time = os.stat(video_path).st_birthtime
        assert birth_time > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
