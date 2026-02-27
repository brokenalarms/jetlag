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
import pytest

from conftest import create_test_video

# Add parent directory to path to import the script
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import hyphenated module name
import importlib.util
spec = importlib.util.spec_from_file_location(
    "fix_media_timestamp",
    str(Path(__file__).parent.parent / "fix-media-timestamp.py")
)
fmt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fmt)


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
        result, pattern = fmt.parse_filename_timestamp(filename)

        assert result == "2025:06:18 07:25:21"
        assert pattern == "YYYYMMDD_HHMMSS"

    def test_parse_filename_dji_pattern(self):
        """Test parsing DJI filename pattern"""
        filename = "/path/to/DJI_20250618072521_0001.mp4"
        result, pattern = fmt.parse_filename_timestamp(filename)

        assert result == "2025:06:18 07:25:21"
        assert pattern == "YYYYMMDDHHMMSS"

    def test_parse_filename_no_match(self):
        """Test that random filenames return None"""
        filename = "/path/to/random_file.mp4"
        result, pattern = fmt.parse_filename_timestamp(filename)

        assert result is None
        assert pattern is None


class TestExifDataReading:
    """Test EXIF data reading functions"""

    def setup_method(self):
        """Create temp directory and test file"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_video = os.path.join(self.temp_dir, "test.mp4")
        create_test_video(self.test_video, DateTimeOriginal="2025:06:18 07:25:21+08:00")

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


class TestChangeDetection:
    """Test functions that determine what needs updating"""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_video = os.path.join(self.temp_dir, "test.mp4")
        create_test_video(self.test_video, DateTimeOriginal="2025:06:18 07:25:21+08:00")

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def test_check_keys_creationdate_needs_update_missing(self):
        """Test detecting missing Keys:CreationDate"""
        dt = datetime(2025, 6, 18, 7, 25, 21, tzinfo=timezone(timedelta(hours=8)))

        needs_update = fmt.check_keys_creationdate_needs_update(
            self.test_video, dt
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
            self.test_video, dt
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
        create_test_video(self.test_video)

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

        success = fmt.write_keys_creationdate(self.test_video, dt)

        assert success is True

        # Verify it was written
        fmt._exif_cache.clear()
        data = fmt.read_exif_data(self.test_video)
        assert "CreationDate" in data


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
        create_test_video(video_path, DateTimeOriginal="2025:06:18 07:25:21+08:00")

        timestamp, source = fmt.get_best_timestamp(video_path)

        assert timestamp == "2025:06:18 07:25:21"
        assert "DateTimeOriginal" in source
        assert "timezone" in source

    def test_priority_3_filename(self):
        """Test Priority 3: Filename pattern"""
        video_path = os.path.join(self.temp_dir, "VID_20250618_072521.mp4")
        create_test_video(video_path)

        timestamp, source = fmt.get_best_timestamp(video_path)

        assert timestamp == "2025:06:18 07:25:21"
        assert "filename" in source


class TestGetAllTimestampData:
    """Test get_all_timestamp_data function - the 5-tier priority system"""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def _create_video(self, filename, exif_args=None):
        """Create test video with optional EXIF data"""
        path = os.path.join(self.temp_dir, filename)
        if exif_args:
            tags = {}
            for arg in exif_args:
                key, value = arg.lstrip("-").split("=", 1)
                tags[key] = value
            create_test_video(path, **tags)
        else:
            create_test_video(path)
        fmt._exif_cache.clear()
        return path

    def test_datetimeoriginal_with_timezone(self):
        """Priority 1: DateTimeOriginal with timezone is source of truth"""
        video = self._create_video("test.mp4", ["-DateTimeOriginal=2025:06:18 07:25:21+08:00"])

        data = fmt.get_all_timestamp_data(video)

        assert data["timestamp_source"] == "DateTimeOriginal with timezone"
        assert data["datetime_original"] is not None
        assert data["datetime_original"].hour == 7
        assert data["datetime_original"].minute == 25
        assert data["datetime_original"].utcoffset() == timedelta(hours=8)

    def test_creationdate_with_timezone(self):
        """Priority 2: Keys:CreationDate with timezone when no DateTimeOriginal"""
        video = self._create_video("test.mp4", ["-Keys:CreationDate=2025:06:18 09:30:00+09:00"])

        data = fmt.get_all_timestamp_data(video)

        assert data["timestamp_source"] == "CreationDate with timezone"
        assert data["datetime_original"] is not None
        assert data["datetime_original"].hour == 9
        assert data["datetime_original"].minute == 30
        assert data["datetime_original"].utcoffset() == timedelta(hours=9)

    def test_creationdate_utc_with_timezone_flag(self):
        """CreationDate with Z (UTC) needs --timezone to convert to local time"""
        video = self._create_video("test.mp4", ["-Keys:CreationDate=2025:06:17 23:25:21Z"])

        data = fmt.get_all_timestamp_data(video, timezone_offset="+08:00")

        assert data["timestamp_source"] == "CreationDate with Z (UTC)"
        assert data["datetime_original"] is not None
        # UTC 23:25:21 + 8 hours = 07:25:21 next day
        assert data["datetime_original"].hour == 7
        assert data["datetime_original"].day == 18
        assert data["datetime_original"].utcoffset() == timedelta(hours=8)

    def test_mediacreatedate_with_timezone_flag(self):
        """MediaCreateDate (UTC) needs --timezone to convert to local time"""
        video = self._create_video("test.mp4", ["-QuickTime:MediaCreateDate=2025:06:17 23:25:21"])

        data = fmt.get_all_timestamp_data(video, timezone_offset="+08:00")

        assert data["timestamp_source"] == "MediaCreateDate"
        assert data["datetime_original"] is not None
        # UTC 23:25:21 + 8 hours = 07:25:21 next day
        assert data["datetime_original"].hour == 7
        assert data["datetime_original"].day == 18

    def test_filename_with_timezone_flag(self):
        """Filename pattern VID_YYYYMMDD_HHMMSS needs --timezone"""
        video = self._create_video("VID_20250618_072521.mp4")

        data = fmt.get_all_timestamp_data(video, timezone_offset="+08:00")

        assert "filename" in data["timestamp_source"]
        assert data["datetime_original"] is not None
        assert data["datetime_original"].hour == 7
        assert data["datetime_original"].minute == 25
        assert data["datetime_original"].second == 21

    def test_infer_from_filename_uses_filename(self):
        """--infer-from-filename uses filename even when EXIF exists"""
        # Filename says 06:38:09, but EXIF says 09:38:09 (corrupted)
        video = self._create_video(
            "VID_20250619_063809.mp4",
            ["-DateTimeOriginal=2025:06:19 09:38:09+08:00"]
        )

        data = fmt.get_all_timestamp_data(
            video,
            timezone_offset="+08:00",
            infer_from_filename=True
        )

        assert data["timestamp_source"] == "filename (infer mode)"
        assert data["datetime_original"].hour == 6  # From filename, not 9 from EXIF
        assert data["datetime_original"].minute == 38
        assert data["datetime_original"].second == 9

    def test_infer_from_filename_requires_timezone(self):
        """--infer-from-filename requires --timezone"""
        video = self._create_video("VID_20250618_072521.mp4")

        with pytest.raises(ValueError) as exc_info:
            fmt.get_all_timestamp_data(video, infer_from_filename=True)

        assert "requires --timezone" in str(exc_info.value)

    def test_infer_from_filename_requires_parseable_name(self):
        """--infer-from-filename with unparseable filename raises error"""
        video = self._create_video("test.mp4", ["-DateTimeOriginal=2025:06:18 07:25:21+08:00"])

        with pytest.raises(ValueError) as exc_info:
            fmt.get_all_timestamp_data(video, timezone_offset="+08:00", infer_from_filename=True)

        assert "no parseable date" in str(exc_info.value)

    def test_datetimeoriginal_without_timezone_adds_flag_timezone(self):
        """DateTimeOriginal without timezone uses --timezone flag"""
        video = self._create_video("test.mp4", ["-DateTimeOriginal=2025:06:18 07:25:21"])

        data = fmt.get_all_timestamp_data(video, timezone_offset="+08:00")

        assert data["timestamp_source"] == "DateTimeOriginal"
        assert data["datetime_original"] is not None
        assert data["datetime_original"].utcoffset() == timedelta(hours=8)
        assert "--timezone flag" in data["timezone_source"]


class TestFormattingFunctions:
    """Test display formatting functions"""

    def test_format_exif_timestamp_display(self):
        """Test EXIF timestamp formatting (colons to dashes for date)"""
        result = fmt.format_exif_timestamp_display("2025:06:18 07:25:21")
        assert result == "2025-06-18 07:25:21"

    def test_format_exif_timestamp_display_empty(self):
        """Test formatting handles empty string"""
        result = fmt.format_exif_timestamp_display("")
        assert result == ""

    def test_format_timestamp_display(self):
        """Test datetime formatting"""
        dt = datetime(2025, 6, 18, 7, 25, 21, tzinfo=timezone(timedelta(hours=8)))
        result = fmt.format_timestamp_display(dt)
        assert result == "2025-06-18 07:25:21+0800"

    def test_format_time_delta_exact_hour(self):
        """Test formatting exact hour delta"""
        result = fmt.format_time_delta(3600)  # 1 hour
        assert result == "+1 hour"

    def test_format_time_delta_multiple_hours(self):
        """Test formatting multiple hours delta"""
        result = fmt.format_time_delta(7200)  # 2 hours
        assert result == "+2 hours"

    def test_format_time_delta_negative(self):
        """Test formatting negative delta"""
        result = fmt.format_time_delta(-3600)  # -1 hour
        assert result == "-1 hour"

    def test_format_time_delta_minutes_only(self):
        """Test formatting minutes only"""
        result = fmt.format_time_delta(1800)  # 30 minutes
        assert result == "+30 minutes"

    def test_format_time_delta_hours_and_minutes(self):
        """Test formatting hours and minutes"""
        result = fmt.format_time_delta(5400)  # 1h 30m
        assert result == "+1h 30m"

    def test_format_time_delta_rounds_to_hour(self):
        """Test that times within 2 minutes of hour round to hour"""
        result = fmt.format_time_delta(3660)  # 1 hour + 1 minute
        assert result == "+1 hour"


class TestLocationTimezone:
    """Test location-based timezone lookup"""

    def test_get_timezone_for_country_code(self):
        """Test getting timezone for country code returns valid format"""
        result = fmt.get_timezone_for_country("JP")
        # Returns None if CSV files don't exist, or a timezone string
        if result is not None:
            # Should be in +HHMM or +HH:MM format
            assert result[0] in ["+", "-"]
            assert len(result) >= 5

    def test_get_timezone_for_invalid_country(self):
        """Test that invalid country returns None"""
        result = fmt.get_timezone_for_country("XX")
        assert result is None

    def test_get_country_name_from_code(self):
        """Test getting country name from code"""
        result = fmt.get_country_name("JP")
        # Should return "Japan" if CSV exists, otherwise "JP"
        assert result in ["Japan", "JP"]

    def test_get_country_name_passthrough(self):
        """Test that unknown country code is returned as-is"""
        result = fmt.get_country_name("Unknown Country")
        assert result == "Unknown Country"


class TestDetermineNeededChanges:
    """Test the determine_needed_changes function"""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_video = os.path.join(self.temp_dir, "test.mp4")
        create_test_video(self.test_video)

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def test_returns_all_required_keys(self):
        """Test that all required change keys are returned"""
        dt = datetime(2025, 6, 18, 7, 25, 21, tzinfo=timezone(timedelta(hours=8)))
        changes = fmt.determine_needed_changes(self.test_video, dt)

        assert "keys_creationdate" in changes
        assert "file_timestamps" in changes
        assert "quicktime_createdate" in changes

    def test_fresh_file_needs_keys_creationdate(self):
        """Test that a fresh file needs Keys:CreationDate"""
        dt = datetime(2025, 6, 18, 7, 25, 21, tzinfo=timezone(timedelta(hours=8)))
        changes = fmt.determine_needed_changes(self.test_video, dt)

        assert changes["keys_creationdate"] is True


if __name__ == "__main__":
    # Run with pytest
    import pytest
    pytest.main([__file__, "-v"])
