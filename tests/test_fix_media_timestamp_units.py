#!/usr/bin/env python3
"""
Unit tests for fix-media-timestamp.py
Tests individual functions without relying on output strings
"""

import os
import sys
import tempfile
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
import subprocess

# Add parent directory to path to import the script
sys.path.insert(0, str(Path(__file__).parent.parent))

import fix_media_timestamp as fmt


class TestTimestampParsing:
    """Test timestamp parsing functions"""

    def test_parse_datetime_original_with_timezone(self):
        """Test parsing DateTimeOriginal with timezone"""
        dt_str = "2025:06:18 07:25:21+08:00"
        result = fmt.parse_datetime_original(dt_str)

        assert result is not None
        assert result.year == 2025
        assert result.month == 6
        assert result.day == 18
        assert result.hour == 7
        assert result.minute == 25
        assert result.second == 21
        # Timezone should be +08:00
        assert result.utcoffset() == timedelta(hours=8)

    def test_parse_datetime_original_negative_timezone(self):
        """Test parsing DateTimeOriginal with negative timezone"""
        dt_str = "2025:06:18 07:25:21-05:00"
        result = fmt.parse_datetime_original(dt_str)

        assert result is not None
        assert result.utcoffset() == timedelta(hours=-5)

    def test_parse_filename_insta360_pattern(self):
        """Test parsing Insta360 filename pattern"""
        filename = "/path/to/VID_20250618_072521.mp4"
        result = fmt.parse_filename_timestamp(filename)

        assert result == "2025:06:18 07:25:21"

    def test_parse_filename_dji_pattern(self):
        """Test parsing DJI filename pattern"""
        filename = "/path/to/DJI_20250618072521_0001.mp4"
        result = fmt.parse_filename_timestamp(filename)

        assert result == "2025:06:18 07:25:21"

    def test_parse_filename_no_match(self):
        """Test that random filenames return None"""
        filename = "/path/to/random_file.mp4"
        result = fmt.parse_filename_timestamp(filename)

        assert result is None


class TestTimestampCalculations:
    """Test timestamp calculation functions"""

    def test_get_expected_file_system_time_display_mode(self):
        """Test file system time calculation in display mode (default)"""
        # Create datetime: 2025-06-18 07:25:21+08:00
        dt = datetime(2025, 6, 18, 7, 25, 21, tzinfo=timezone(timedelta(hours=8)))

        # Without preserve_wallclock, should convert to local timezone
        result = fmt.get_expected_file_system_time(dt, preserve_wallclock=False)

        # Result should be a local time string
        assert result is not None
        assert "2025:06:18" in result
        # Time will depend on system timezone, so just check format
        assert len(result.split()) == 2  # "YYYY:MM:DD HH:MM:SS"

    def test_get_expected_file_system_time_wallclock_mode(self):
        """Test file system time calculation in wallclock mode"""
        dt = datetime(2025, 6, 18, 7, 25, 21, tzinfo=timezone(timedelta(hours=8)))

        # With preserve_wallclock, should keep shooting time
        result = fmt.get_expected_file_system_time(dt, preserve_wallclock=True)

        assert result == "2025:06:18 07:25:21"


class TestExifDataReading:
    """Test EXIF data reading functions"""

    def setup_method(self):
        """Create temp directory and test file"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_video = os.path.join(self.temp_dir, "test.mp4")

        # Create test video
        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            self.test_video
        ], capture_output=True, check=True)

        # Set DateTimeOriginal
        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            "-DateTimeOriginal=2025:06:18 07:25:21+08:00",
            self.test_video
        ], capture_output=True, check=True)

    def teardown_method(self):
        """Clean up temp directory"""
        shutil.rmtree(self.temp_dir)
        # Clear EXIF cache
        fmt._exif_cache.clear()

    def test_read_exif_data(self):
        """Test reading EXIF data from file"""
        data = fmt.read_exif_data(self.test_video)

        assert "DateTimeOriginal" in data
        assert "2025:06:18 07:25:21" in data["DateTimeOriginal"]

    def test_exif_cache(self):
        """Test that EXIF data is cached"""
        # First read
        data1 = fmt.read_exif_data(self.test_video)

        # Second read should use cache
        data2 = fmt.read_exif_data(self.test_video)

        assert data1 == data2
        # Verify cache was used
        assert self.test_video in fmt._exif_cache

    def test_get_file_system_timestamps(self):
        """Test reading file system timestamps"""
        timestamps = fmt.get_file_system_timestamps(self.test_video)

        assert "birth" in timestamps
        assert "modify" in timestamps
        assert len(timestamps["birth"]) > 0
        assert len(timestamps["modify"]) > 0


class TestChangeDetection:
    """Test functions that determine what needs updating"""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_video = os.path.join(self.temp_dir, "test.mp4")

        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            self.test_video
        ], capture_output=True, check=True)

        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            "-DateTimeOriginal=2025:06:18 07:25:21+08:00",
            self.test_video
        ], capture_output=True, check=True)

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def test_check_keys_creationdate_needs_update_missing(self):
        """Test detecting missing Keys:CreationDate"""
        dt = datetime(2025, 6, 18, 7, 25, 21, tzinfo=timezone(timedelta(hours=8)))

        needs_update = fmt.check_keys_creationdate_needs_update(
            self.test_video, dt, preserve_wallclock=False
        )

        # Should need update if Keys:CreationDate is missing
        assert needs_update is True

    def test_check_keys_creationdate_needs_update_correct(self):
        """Test detecting correct Keys:CreationDate"""
        dt = datetime(2025, 6, 18, 7, 25, 21, tzinfo=timezone(timedelta(hours=8)))

        # Set Keys:CreationDate
        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            "-Keys:CreationDate=2025:06:18 07:25:21+08:00",
            self.test_video
        ], capture_output=True, check=True)

        # Clear cache to force re-read
        fmt._exif_cache.clear()

        needs_update = fmt.check_keys_creationdate_needs_update(
            self.test_video, dt, preserve_wallclock=False
        )

        # Should NOT need update if already correct
        assert needs_update is False

    def test_determine_needed_changes(self):
        """Test determining all needed changes"""
        dt = datetime(2025, 6, 18, 7, 25, 21, tzinfo=timezone(timedelta(hours=8)))

        changes = fmt.determine_needed_changes(self.test_video, dt, preserve_wallclock=False)

        assert isinstance(changes, dict)
        assert "keys_creationdate" in changes
        assert "file_timestamps" in changes
        assert "quicktime_createdate" in changes
        # All should be boolean
        assert isinstance(changes["keys_creationdate"], bool)


class TestWriteOperations:
    """Test write operations and idempotency"""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_video = os.path.join(self.temp_dir, "test.mp4")

        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            self.test_video
        ], capture_output=True, check=True)

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def test_write_datetime_original(self):
        """Test writing DateTimeOriginal"""
        dt_str = "2025:06:18 07:25:21+08:00"

        success = fmt.write_datetime_original(self.test_video, dt_str)

        assert success is True

        # Verify it was written
        fmt._exif_cache.clear()
        data = fmt.read_exif_data(self.test_video)
        assert "DateTimeOriginal" in data
        assert "2025:06:18 07:25:21" in data["DateTimeOriginal"]

    def test_write_keys_creationdate(self):
        """Test writing Keys:CreationDate"""
        dt = datetime(2025, 6, 18, 7, 25, 21, tzinfo=timezone(timedelta(hours=8)))

        success = fmt.write_keys_creationdate(self.test_video, dt, preserve_wallclock=False)

        assert success is True

        # Verify it was written
        fmt._exif_cache.clear()
        data = fmt.read_exif_data(self.test_video)
        assert "CreationDate" in data

    def test_set_file_system_timestamps_birth_only(self):
        """Test that only birth time is set, not modification time"""
        timestamp_str = "2025:06:18 07:25:21"

        # Get current mtime
        original_mtime = os.stat(self.test_video).st_mtime

        success = fmt.set_file_system_timestamps(self.test_video, timestamp_str)

        assert success is True

        # Birth time should be set
        new_stat = os.stat(self.test_video)
        new_birthtime = new_stat.st_birthtime

        # Parse expected time
        expected_dt = datetime.strptime(timestamp_str, '%Y:%m:%d %H:%M:%S')

        # Birth time should match (within tolerance)
        birthtime_dt = datetime.fromtimestamp(new_birthtime)
        diff = abs((birthtime_dt - expected_dt).total_seconds())
        assert diff < 2  # 2 second tolerance

        # Modification time should NOT be artificially set
        # (it may change due to file operations, but shouldn't be set to the target time)
        new_mtime = new_stat.st_mtime
        # If mtime changed, it should be current time, not the target time
        if new_mtime != original_mtime:
            mtime_dt = datetime.fromtimestamp(new_mtime)
            now = datetime.now()
            # Should be close to now, not the target time
            assert abs((mtime_dt - now).total_seconds()) < 10


class TestTimezoneHandling:
    """Test timezone-related functions"""

    def test_normalize_timezone_input_adds_plus(self):
        """Test that timezone normalization adds + sign"""
        result = fmt.normalize_timezone_input("0800")
        assert result == "+08:00"

    def test_normalize_timezone_input_preserves_minus(self):
        """Test that negative timezones are preserved"""
        result = fmt.normalize_timezone_input("-0500")
        assert result == "-05:00"

    def test_normalize_timezone_input_adds_colon(self):
        """Test that colon is added to timezone"""
        result = fmt.normalize_timezone_input("+0800")
        assert result == "+08:00"

    def test_normalize_timezone_input_preserves_colon(self):
        """Test that existing colon is preserved"""
        result = fmt.normalize_timezone_input("+08:00")
        assert result == "+08:00"


class TestBestTimestampPriority:
    """Test the 5-tier priority system for finding best timestamp"""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def test_priority_1_datetimeoriginal_with_tz(self):
        """Test Priority 1: DateTimeOriginal with timezone"""
        video_path = os.path.join(self.temp_dir, "test.mp4")

        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            video_path
        ], capture_output=True, check=True)

        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            "-DateTimeOriginal=2025:06:18 07:25:21+08:00",
            video_path
        ], capture_output=True, check=True)

        timestamp, source = fmt.get_best_timestamp(video_path)

        assert timestamp == "2025:06:18 07:25:21"
        assert "DateTimeOriginal" in source
        assert "timezone" in source

    def test_priority_3_filename(self):
        """Test Priority 3: Filename pattern"""
        video_path = os.path.join(self.temp_dir, "VID_20250618_072521.mp4")

        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            video_path
        ], capture_output=True, check=True)

        timestamp, source = fmt.get_best_timestamp(video_path)

        assert timestamp == "2025:06:18 07:25:21"
        assert "filename" in source


if __name__ == "__main__":
    # Run with pytest
    import pytest
    pytest.main([__file__, "-v"])
