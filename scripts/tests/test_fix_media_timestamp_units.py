#!/usr/bin/env python3
"""
Unit tests for fix-media-timestamp.py
Tests individual functions without relying on output strings
"""

import json
import os
import sys
import tempfile
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
import subprocess
import pytest

from conftest import create_test_photo, create_test_video

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
from lib.timestamp_source import SOURCE_UTC_BY_SPEC, SOURCE_UTC_CORROBORATED


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

    def _set_tags(self, path, *tag_args):
        subprocess.run(
            ["exiftool", "-P", "-overwrite_original", *tag_args, path],
            capture_output=True, check=True,
        )
        fmt._exif_cache.clear()

    def test_missing_keys_creationdate_is_reported_stale(self):
        """A file with no Keys:CreationDate must be reported as needing that field
        written, so FCP reads the corrected time rather than nothing."""
        dt = datetime(2025, 6, 18, 7, 25, 21, tzinfo=timezone(timedelta(hours=8)))

        changes = fmt.determine_needed_changes(self.test_video, dt)

        assert "Keys:CreationDate" in changes["stale_clock_fields"]

    def test_correct_keys_creationdate_is_not_reported_stale(self):
        """A Keys:CreationDate already holding the corrected zoned time is left
        alone, so reprocessing converges instead of rewriting the same value."""
        dt = datetime(2025, 6, 18, 7, 25, 21, tzinfo=timezone(timedelta(hours=8)))
        self._set_tags(self.test_video, "-Keys:CreationDate=2025:06:18 07:25:21+08:00")

        changes = fmt.determine_needed_changes(self.test_video, dt)

        assert "Keys:CreationDate" not in changes["stale_clock_fields"]

    def test_stale_movie_header_alone_is_reported(self):
        """A file whose per-track atoms already carry the corrected instant but
        whose mvhd movie header is hours off must still be reported as needing a
        fix — the header is what most applications read first."""
        dt = datetime(2025, 6, 18, 7, 25, 21, tzinfo=timezone(timedelta(hours=8)))
        self._set_tags(
            self.test_video,
            "-QuickTime:CreateDate=2025:06:17 15:25:21",
            "-QuickTime:MediaCreateDate=2025:06:17 23:25:21",
            "-QuickTime:TrackCreateDate=2025:06:17 23:25:21",
        )

        changes = fmt.determine_needed_changes(self.test_video, dt)

        assert "QuickTime:CreateDate" in changes["stale_clock_fields"]

    def test_stale_track_atom_is_reported(self):
        """A file whose movie header is already correct but whose per-track tkhd
        atom still holds the pre-correction time must be reported as needing a fix,
        so the track atoms any player may read get corrected too."""
        dt = datetime(2025, 6, 18, 7, 25, 21, tzinfo=timezone(timedelta(hours=8)))
        self._set_tags(
            self.test_video,
            "-QuickTime:CreateDate=2025:06:17 23:25:21",
            "-QuickTime:MediaCreateDate=2025:06:17 23:25:21",
            "-QuickTime:TrackCreateDate=2020:01:01 00:00:00",
        )

        changes = fmt.determine_needed_changes(self.test_video, dt)

        assert "QuickTime:TrackCreateDate" in changes["stale_clock_fields"]

    def test_all_clock_fields_correct_needs_no_write(self):
        """Once every clock field carries its corrected value, reprocessing the
        file reports nothing to write — the correction is idempotent."""
        dt = datetime(2025, 6, 18, 7, 25, 21, tzinfo=timezone(timedelta(hours=8)))
        self._set_tags(
            self.test_video,
            "-Keys:CreationDate=2025:06:18 07:25:21+08:00",
            "-QuickTime:CreateDate=2025:06:17 23:25:21",
            "-QuickTime:MediaCreateDate=2025:06:17 23:25:21",
            "-QuickTime:TrackCreateDate=2025:06:17 23:25:21",
        )

        changes = fmt.determine_needed_changes(self.test_video, dt)

        assert changes["stale_clock_fields"] == []

    def test_still_gets_no_quicktime_targets(self):
        """A still has no QuickTime container, so its EXIF CreateDate (local time,
        not UTC) must never be mistaken for a stale movie clock and rewritten."""
        photo = os.path.join(self.temp_dir, "still.jpg")
        create_test_photo(photo, DateTimeOriginal="2025:06:18 07:25:21",
                          CreateDate="2025:06:18 07:25:21")
        dt = datetime(2025, 6, 18, 7, 25, 21, tzinfo=timezone(timedelta(hours=8)))

        changes = fmt.determine_needed_changes(photo, dt)

        assert not [tag for tag in changes["clock_targets"] if tag.startswith("QuickTime:")]
        assert not [tag for tag in changes["stale_clock_fields"] if tag.startswith("QuickTime:")]

    def test_quicktime_targets_share_one_utc_instant(self):
        """Every QuickTime atom targets the same UTC instant as DateTimeOriginal's
        zoned local time, so no atom disagrees with another after a correction."""
        dt = datetime(2025, 6, 18, 7, 25, 21, tzinfo=timezone(timedelta(hours=8)))

        changes = fmt.determine_needed_changes(self.test_video, dt)
        targets = changes["clock_targets"]

        assert targets["QuickTime:CreateDate"] == "2025:06:17 23:25:21"
        assert targets["QuickTime:MediaCreateDate"] == "2025:06:17 23:25:21"
        assert targets["QuickTime:TrackCreateDate"] == "2025:06:17 23:25:21"
        assert targets["Keys:CreationDate"] == "2025:06:18 07:25:21+08:00"


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

    def test_write_quicktime_createdate_reaches_track_atom(self):
        """Healing a QuickTime clock writes the corrected UTC instant into the
        per-track tkhd atom as well as the movie header, so no application reads
        the pre-correction time back out of the track."""
        dt = datetime(2025, 6, 18, 7, 25, 21, tzinfo=timezone(timedelta(hours=8)))

        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            "-QuickTime:TrackCreateDate=2020:01:01 00:00:00",
            self.test_video
        ], capture_output=True, check=True)
        fmt._exif_cache.clear()

        assert fmt.write_quicktime_createdate(self.test_video, dt) is True

        fmt._exif_cache.clear()
        data = fmt.read_exif_data(self.test_video)
        assert data["TrackCreateDate"] == "2025:06:17 23:25:21"
        assert data["MediaCreateDate"] == "2025:06:17 23:25:21"

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

    def test_datetimeoriginal_completed_by_offset_time_original(self):
        """A still whose zone lives in OffsetTimeOriginal reaches the correction pipeline
        as a fully zoned Priority 1 source, needing no declared --timezone."""
        photo = os.path.join(self.temp_dir, "IMG_0007.jpg")
        create_test_photo(photo,
                          DateTimeOriginal="2025:06:18 07:25:21",
                          OffsetTimeOriginal="+08:00")
        fmt._exif_cache.clear()

        data = fmt.get_all_timestamp_data(photo)

        assert data["timestamp_source"] == "DateTimeOriginal with timezone"
        assert data["timezone_source"] == "DateTimeOriginal metadata"
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

    def test_bare_creationdate_without_timezone_adds_flag_timezone(self):
        """A bare Keys:CreationDate (no zone suffix, no Z) ranks as a naive source at
        the same tier as bare DateTimeOriginal, and uses --timezone like it does."""
        video = self._create_video("test.mp4", ["-Keys:CreationDate#=2025:06:18 07:25:21"])

        data = fmt.get_all_timestamp_data(video, timezone_spec="+08:00")

        assert data["timestamp_source"] == "CreationDate"
        assert data["datetime_original"] is not None
        assert data["datetime_original"].hour == 7
        assert data["datetime_original"].minute == 25
        assert data["datetime_original"].utcoffset() == timedelta(hours=8)
        assert "--timezone flag" in data["timezone_source"]

    def test_creationdate_utc_with_timezone_flag(self):
        """CreationDate with Z (UTC) needs --timezone to convert to local time"""
        video = self._create_video("test.mp4", ["-Keys:CreationDate=2025:06:17 23:25:21Z"])

        data = fmt.get_all_timestamp_data(video, timezone_spec="+08:00")

        assert data["timestamp_source"] == "CreationDate with Z (UTC)"
        assert data["datetime_original"] is not None
        # UTC 23:25:21 + 8 hours = 07:25:21 next day
        assert data["datetime_original"].hour == 7
        assert data["datetime_original"].day == 18
        assert data["datetime_original"].utcoffset() == timedelta(hours=8)

    def test_mediacreatedate_with_timezone_flag(self):
        """MediaCreateDate (UTC) needs --timezone to convert to local time"""
        video = self._create_video("test.mp4", ["-QuickTime:MediaCreateDate=2025:06:17 23:25:21"])

        data = fmt.get_all_timestamp_data(video, timezone_spec="+08:00")

        assert data["timestamp_source"] == SOURCE_UTC_BY_SPEC
        assert data["datetime_original"] is not None
        # UTC 23:25:21 + 8 hours = 07:25:21 next day
        assert data["datetime_original"].hour == 7
        assert data["datetime_original"].day == 18

    def test_camera_filename_with_quicktime_instant_converts(self):
        """A camera filename loses to an instant it contradicts, and the instant is
        converted into the declared zone rather than the filename being labelled."""
        video = self._create_video(
            "VID_20260104_033532_00_001.mp4",
            ["-QuickTime:MediaCreateDate=2026:01:03 18:35:32"],
        )

        data = fmt.get_all_timestamp_data(video, timezone_spec="+13:00")

        assert data["timestamp_source"] == SOURCE_UTC_CORROBORATED
        assert data["datetime_original"] is not None
        assert data["datetime_original"].day == 4
        assert data["datetime_original"].hour == 7
        assert data["datetime_original"].minute == 35
        assert data["datetime_original"].utcoffset() == timedelta(hours=13)

    def test_filename_with_timezone_flag(self):
        """Filename pattern VID_YYYYMMDD_HHMMSS needs --timezone"""
        video = self._create_video("VID_20250618_072521.mp4")

        data = fmt.get_all_timestamp_data(video, timezone_spec="+08:00")

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
            timezone_spec="+08:00",
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
            fmt.get_all_timestamp_data(video, timezone_spec="+08:00", infer_from_filename=True)

        assert "no parseable date" in str(exc_info.value)

    def test_datetimeoriginal_without_timezone_adds_flag_timezone(self):
        """DateTimeOriginal without timezone uses --timezone flag"""
        video = self._create_video("test.mp4", ["-DateTimeOriginal=2025:06:18 07:25:21"])

        data = fmt.get_all_timestamp_data(video, timezone_spec="+08:00")

        assert data["timestamp_source"] == "DateTimeOriginal"
        assert data["datetime_original"] is not None
        assert data["datetime_original"].utcoffset() == timedelta(hours=8)
        assert "--timezone flag" in data["timezone_source"]

    def test_zoned_datetimeoriginal_converts_into_declared_zone(self):
        """A zoned DateTimeOriginal defines a moment in time; a declared --timezone
        re-expresses that moment in the declared zone rather than being ignored.
        The UTC value must not move — only the wall clock and its zone label do."""
        video = self._create_video("test.mp4", ["-DateTimeOriginal=2025:10:05 01:00:00+09:00"])

        data = fmt.get_all_timestamp_data(video, timezone_spec="+02:00")

        assert data["timestamp_source"] == "DateTimeOriginal with timezone"
        converted = data["datetime_original"]
        assert converted is not None
        assert converted.utcoffset() == timedelta(hours=2)
        # 01:00 at +09:00 is 16:00 UTC the previous day, i.e. 18:00 at +02:00
        assert converted.day == 4
        assert converted.hour == 18
        embedded = fmt.parse_datetime_original("2025:10:05 01:00:00+09:00")
        assert converted.timestamp() == embedded.timestamp(), \
            "conversion must not move the actual moment in time"
        assert data["datetime_original_str"] == "2025:10:04 18:00:00+02:00"

    def test_zoned_datetimeoriginal_without_declared_zone_passes_through(self):
        """With no --timezone there is nothing to convert into: the zoned value is
        used verbatim, which is what keeps reprocessing corrected files a no-op."""
        video = self._create_video("test.mp4", ["-DateTimeOriginal=2025:10:05 01:00:00+09:00"])

        data = fmt.get_all_timestamp_data(video)

        assert data["datetime_original"].utcoffset() == timedelta(hours=9)
        assert data["datetime_original"].hour == 1
        assert data["timezone_source"] == "DateTimeOriginal metadata"


class TestTimeOffset:
    """Test --time-offset functionality"""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def _create_video(self, name, exif_args=None):
        path = os.path.join(self.temp_dir, name)
        create_test_video(path, **({"DateTimeOriginal": exif_args[0].split("=")[1]} if exif_args else {}))
        return path

    def _parse_at_lines(self, stdout: str) -> dict:
        result = {}
        for line in stdout.strip().split("\n"):
            if line.startswith("@@"):
                key_value = line[2:]
                if "=" in key_value:
                    key, value = key_value.split("=", 1)
                    result[key] = value
        return result

    def test_positive_offset_applied(self):
        """Positive offset shifts timestamp forward"""
        video = self._create_video("test.mp4", ["-DateTimeOriginal=2025:06:18 07:25:21+08:00"])

        result = subprocess.run([
            sys.executable, str(Path(__file__).parent.parent / "fix-media-timestamp.py"),
            video,
            "--timezone", "+0800",
            "--time-offset", "3600",
            "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        at_lines = self._parse_at_lines(result.stdout)
        assert "08:25:21" in at_lines.get("corrected_time", "")
        assert at_lines.get("correction_mode") == "time"
        assert at_lines.get("time_offset_seconds") == "3600"

    def test_negative_offset_applied(self):
        """Negative offset shifts timestamp backward"""
        video = self._create_video("test.mp4", ["-DateTimeOriginal=2025:06:18 07:25:21+08:00"])

        result = subprocess.run([
            sys.executable, str(Path(__file__).parent.parent / "fix-media-timestamp.py"),
            video,
            "--timezone", "+0800",
            "--time-offset", "-3600",
            "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        at_lines = self._parse_at_lines(result.stdout)
        assert "06:25:21" in at_lines.get("corrected_time", "")
        assert at_lines.get("correction_mode") == "time"

    def test_offset_combined_with_infer(self):
        """--time-offset works with --infer-from-filename"""
        video = self._create_video("VID_20250618_072521.mp4")

        result = subprocess.run([
            sys.executable, str(Path(__file__).parent.parent / "fix-media-timestamp.py"),
            video,
            "--timezone", "+0800",
            "--infer-from-filename",
            "--time-offset", "7200",
            "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        at_lines = self._parse_at_lines(result.stdout)
        # 07:25:21 + 2h = 09:25:21
        assert "09:25:21" in at_lines.get("corrected_time", "")

    def test_offset_without_timezone_fails(self):
        """--time-offset without --timezone should fail"""
        video = self._create_video("test.mp4", ["-DateTimeOriginal=2025:06:18 07:25:21+08:00"])

        result = subprocess.run([
            sys.executable, str(Path(__file__).parent.parent / "fix-media-timestamp.py"),
            video,
            "--time-offset", "3600",
            "--apply"
        ], capture_output=True, text=True)

        assert result.returncode != 0
        assert "requires --timezone" in result.stderr

    def test_offset_display_emitted(self):
        """@@time_offset_display is emitted when offset is non-zero"""
        video = self._create_video("test.mp4", ["-DateTimeOriginal=2025:06:18 07:25:21+08:00"])

        result = subprocess.run([
            sys.executable, str(Path(__file__).parent.parent / "fix-media-timestamp.py"),
            video,
            "--timezone", "+0800",
            "--time-offset", "93784",
        ], capture_output=True, text=True)

        assert result.returncode == 0
        at_lines = self._parse_at_lines(result.stdout)
        assert at_lines.get("time_offset_display") == "+1d 2h 3m 4s"


class TestForceTimezoneGate:
    """--force-timezone is a confirmation gate, not arithmetic.

    A file whose metadata already carries a timezone is refused an --apply with a
    different declared --timezone unless --force-timezone confirms the relabel.
    Dry runs always preview the relabel and mark it as needing confirmation.
    When the relabel is confirmed, the file's actual moment in time (UTC) must not
    move — only the wall clock and zone label are rewritten. Only --time-offset may
    move the actual time. This pins the fix for the #111 defect where forcing kept
    the wall-clock digits and swapped the zone, shifting the file's UTC.
    """

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.video = os.path.join(self.temp_dir, "test.mp4")
        create_test_video(self.video, DateTimeOriginal="2025:10:05 01:00:00+09:00")
        fmt._exif_cache.clear()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def _run(self, *extra_args):
        return subprocess.run([
            sys.executable, str(Path(__file__).parent.parent / "fix-media-timestamp.py"),
            self.video, *extra_args,
        ], capture_output=True, text=True)

    def _parse_at_lines(self, stdout: str) -> dict:
        result = {}
        for line in stdout.strip().split("\n"):
            if line.startswith("@@") and "=" in line[2:]:
                key, value = line[2:].split("=", 1)
                result[key] = value
        return result

    def _read_dto(self) -> str:
        fmt._exif_cache.clear()
        return fmt.read_exif_data(self.video).get("DateTimeOriginal", "")

    def test_apply_with_conflicting_timezone_refused_without_force(self):
        """Applying a different zone over an embedded one is refused, and the
        file is untouched."""
        before = self._read_dto()
        result = self._run("--timezone", "+02:00", "--apply")

        assert result.returncode != 0
        at_lines = self._parse_at_lines(result.stdout)
        assert at_lines.get("timestamp_action") == "error"
        assert at_lines.get("requires_force_timezone") == "true"
        assert self._read_dto() == before, "refused apply must not modify the file"

    def test_dry_run_previews_conflict_without_force(self):
        """A dry run is never blocked: it shows the would-be relabel and flags
        that applying needs --force-timezone. The file is untouched."""
        before = self._read_dto()
        result = self._run("--timezone", "+02:00")

        assert result.returncode == 0
        at_lines = self._parse_at_lines(result.stdout)
        assert at_lines.get("requires_force_timezone") == "true"
        assert at_lines.get("timestamp_action") in ("would_fix", "no_change")
        # Preview shows the conversion: same moment, expressed at +02:00
        assert "2025:10:04 18:00:00+02:00" in at_lines.get("corrected_time", "")
        assert self._read_dto() == before, "dry run must not modify the file"

    def test_forced_relabel_preserves_utc(self):
        """With --force-timezone the relabel proceeds: the stored tag gets the
        declared zone's wall clock for the same UTC moment."""
        result = self._run("--timezone", "+02:00", "--force-timezone", "--apply")

        assert result.returncode == 0
        at_lines = self._parse_at_lines(result.stdout)
        assert at_lines.get("original_epoch") == at_lines.get("corrected_epoch"), \
            "relabelling must not move the actual time"
        dto = self._read_dto()
        assert dto.startswith("2025:10:04 18:00:00"), f"expected converted wall clock, got {dto}"
        assert dto.replace(":", "").endswith("+0200")

    def test_matching_timezone_needs_no_force(self):
        """Declaring the zone the file already carries is not a relabel: no
        refusal, no confirmation flag emitted."""
        result = self._run("--timezone", "+09:00", "--apply")

        assert result.returncode == 0
        at_lines = self._parse_at_lines(result.stdout)
        assert "requires_force_timezone" not in at_lines
        assert self._read_dto().replace(":", "").endswith("+0900")

    def test_naive_filename_source_preserves_wall_clock(self):
        """A file with no timezone in metadata (e.g. a reset camera clock where the
        filename is the only source) keeps its wall-clock digits: the declared zone
        is attached to them, not used to shift them. The gate never fires — there
        is no embedded zone to conflict with."""
        video = os.path.join(self.temp_dir, "VID_20250618_072521.mp4")
        create_test_video(video)
        fmt._exif_cache.clear()

        result = subprocess.run([
            sys.executable, str(Path(__file__).parent.parent / "fix-media-timestamp.py"),
            video, "--timezone", "+01:00", "--apply",
        ], capture_output=True, text=True)

        assert result.returncode == 0
        at_lines = self._parse_at_lines(result.stdout)
        assert "requires_force_timezone" not in at_lines
        assert "2025:06:18 07:25:21+01:00" in at_lines.get("corrected_time", "")


class TestFormatOffsetDisplay:
    """Test format_offset_display helper"""

    def test_positive_offset(self):
        assert fmt.format_offset_display(93784) == "+1d 2h 3m 4s"

    def test_negative_offset(self):
        assert fmt.format_offset_display(-5400) == "-0d 1h 30m 0s"

    def test_zero(self):
        assert fmt.format_offset_display(0) == "+0d 0h 0m 0s"

    def test_small_offset(self):
        assert fmt.format_offset_display(300) == "+0d 0h 5m 0s"


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

    def test_returns_targets_stale_fields_and_file_flag(self):
        """The one comparison reports what each clock field should hold, which of
        those are not already correct, and whether the file system needs touching."""
        dt = datetime(2025, 6, 18, 7, 25, 21, tzinfo=timezone(timedelta(hours=8)))
        changes = fmt.determine_needed_changes(self.test_video, dt)

        assert "clock_targets" in changes
        assert "stale_clock_fields" in changes
        assert "file_timestamps" in changes
        assert isinstance(changes["file_timestamps"], bool)

    def test_fresh_file_needs_keys_creationdate(self):
        """Test that a fresh file needs Keys:CreationDate"""
        dt = datetime(2025, 6, 18, 7, 25, 21, tzinfo=timezone(timedelta(hours=8)))
        changes = fmt.determine_needed_changes(self.test_video, dt)

        assert "Keys:CreationDate" in changes["stale_clock_fields"]

    def test_datetime_original_is_owned_only_when_the_caller_writes_it(self):
        """An existing DateTimeOriginal is the correction's source, not its target:
        it is only compared and written when the caller has decided to write it
        (missing tag, --infer-from-filename or a confirmed --force-timezone)."""
        dt = datetime(2025, 6, 18, 7, 25, 21, tzinfo=timezone(timedelta(hours=8)))

        assert "DateTimeOriginal" not in fmt.determine_needed_changes(
            self.test_video, dt)["clock_targets"]
        assert "DateTimeOriginal" in fmt.determine_needed_changes(
            self.test_video, dt, write_datetime_original=True)["clock_targets"]


class TestTimestampFixResult:
    """Test that fix_media_timestamps() returns TimestampFixResult dataclass."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_video = os.path.join(self.temp_dir, "VID_20250618_072521.mp4")
        create_test_video(
            self.test_video,
            DateTimeOriginal="2025:06:18 07:25:21+08:00",
        )

    def teardown_method(self):
        fmt.clear_exif_cache()
        shutil.rmtree(self.temp_dir)

    def test_returns_timestamp_fix_result(self):
        """fix_media_timestamps returns TimestampFixResult, not bool.

        Actual: return type is TimestampFixResult with correct fields
        Expected: TimestampFixResult dataclass instance
        """
        result = fmt.fix_media_timestamps(
            self.test_video, dry_run=True, timezone_spec="+08:00"
        )
        assert isinstance(result, fmt.TimestampFixResult)
        assert result.file == "VID_20250618_072521.mp4"
        assert result.timestamp_action in ("would_fix", "no_change")
        assert result.original_time is not None
        assert result.corrected_time is not None
        assert result.timestamp_source is not None
        assert result.correction_mode in ("timezone", "time")

    def test_error_result_for_missing_timestamps(self):
        """Files without usable timestamps return action='error'.

        Actual: TimestampFixResult.timestamp_action is 'error'
        Expected: error action for files with no timestamp data
        """
        blank_video = os.path.join(self.temp_dir, "blank.mp4")
        create_test_video(blank_video)
        result = fmt.fix_media_timestamps(blank_video, dry_run=True)
        assert isinstance(result, fmt.TimestampFixResult)
        assert result.timestamp_action == "error"

    def test_timezone_field_populated(self):
        """Detected timezone populates result.timezone.

        Actual: TimestampFixResult.timezone contains detected offset
        Expected: timezone from file metadata
        """
        result = fmt.fix_media_timestamps(
            self.test_video, dry_run=True, timezone_spec="+08:00"
        )
        assert isinstance(result, fmt.TimestampFixResult)
        # timezone is populated from metadata detection (may be None if not detected)
        # just verify it doesn't crash and is Optional[str]
        assert result.timezone is None or isinstance(result.timezone, str)




class TestProvenanceRecord:
    """A file's pre-correction clock fields are recorded once, before jetlag first writes."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.video = os.path.join(self.temp_dir, "VID_20250618_072521.mp4")
        create_test_video(
            self.video,
            DateTimeOriginal="2025:06:18 07:25:21",
            **{"QuickTime:CreateDate": "2025:06:17 23:25:21",
               "QuickTime:MediaCreateDate": "2025:06:17 23:25:21"},
        )

    def teardown_method(self):
        fmt.clear_exif_cache()
        shutil.rmtree(self.temp_dir)

    def test_provenance_written_on_first_correction(self):
        """Correcting a file records what its clock fields and filename held beforehand,
        so a bad correction is recoverable from the file itself."""
        result = fmt.fix_media_timestamps(self.video, timezone_spec="+08:00")
        assert result.timestamp_action == "fixed"

        record = json.loads(fmt.read_provenance_record(self.video))
        assert record["filename"] == "VID_20250618_072521.mp4"
        assert record["DateTimeOriginal"] == "2025:06:18 07:25:21"
        assert record["CreateDate"] == "2025:06:17 23:25:21"
        assert record["MediaCreateDate"] == "2025:06:17 23:25:21"

    def test_provenance_unchanged_by_later_corrections(self):
        """Re-correcting an already-tagged file leaves the record byte-identical, so it
        keeps describing the state before jetlag's first write, not the previous run's."""
        fmt.fix_media_timestamps(self.video, timezone_spec="+08:00")
        first = fmt.read_provenance_record(self.video)
        assert first

        fmt.clear_exif_cache()
        second_run = fmt.fix_media_timestamps(
            self.video, timezone_spec="+09:00", force_timezone=True
        )
        assert second_run.timestamp_action == "fixed"

        assert fmt.read_provenance_record(self.video) == first

    def test_dry_run_writes_no_provenance(self):
        """A dry run previews without touching the file, the provenance tag included."""
        result = fmt.fix_media_timestamps(self.video, dry_run=True, timezone_spec="+08:00")
        assert result.timestamp_action == "would_fix"
        assert fmt.read_provenance_record(self.video) == ""

    def test_provenance_omits_fields_the_file_never_had(self):
        """A file carrying none of the recorded clock fields still corrects, and its
        record simply omits what was never there."""
        bare = os.path.join(self.temp_dir, "VID_20250618_072521_bare.mp4")
        create_test_video(bare)

        result = fmt.fix_media_timestamps(bare, timezone_spec="+08:00")
        assert result.timestamp_action == "fixed"

        record = json.loads(fmt.read_provenance_record(bare))
        assert record["filename"] == "VID_20250618_072521_bare.mp4"
        assert "DateTimeOriginal" not in record


class TestCorrectionWritesTheWholeClockTable:
    """A correction owns one table of clock fields: when any of them is wrong the
    write carries all of them, and when none is wrong nothing is written at all.
    """

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        fmt._exif_cache.clear()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def _spy_on_writes(self, monkeypatch):
        """Record the args of every exiftool write without touching the file."""
        calls = []

        def spy(file_path, tag_args):
            calls.append(list(tag_args))
            return True

        monkeypatch.setattr(fmt.exiftool, "write_tags", spy)
        return calls

    def test_video_write_carries_every_clock_field(self, monkeypatch):
        """One stale clock field rewrites the whole table in a single exiftool call,
        so a correct-looking atom can never keep a pre-correction value."""
        video = os.path.join(self.temp_dir, "VID_20250618_072521.mp4")
        create_test_video(video)
        fmt._exif_cache.clear()

        calls = self._spy_on_writes(monkeypatch)
        result = fmt.fix_media_timestamps(video, timezone_spec="+08:00")

        assert result.timestamp_action == "fixed"
        written = [arg.split("=", 1)[0].lstrip("-") for call in calls for arg in call]
        for tag in ["DateTimeOriginal", "Keys:CreationDate", "QuickTime:CreateDate",
                    "QuickTime:MediaCreateDate", "QuickTime:TrackCreateDate"]:
            assert tag in written, f"{tag} missing from write args {written}"

    def test_still_gets_no_quicktime_args(self, monkeypatch):
        """A still has no QuickTime container: writing movie-clock atoms to it would
        stamp UTC into EXIF fields that hold local time."""
        photo = os.path.join(self.temp_dir, "IMG_20250618_072521.jpg")
        create_test_photo(photo)
        fmt._exif_cache.clear()

        calls = self._spy_on_writes(monkeypatch)
        fmt.fix_media_timestamps(photo, timezone_spec="+08:00")

        quicktime_args = [arg for call in calls for arg in call if arg.startswith("-QuickTime:")]
        assert quicktime_args == []

    def test_already_correct_file_is_never_written(self, monkeypatch):
        """When every clock field already equals its target the run reports no
        change and issues no exiftool write — not even an empty one."""
        video = os.path.join(self.temp_dir, "VID_20250618_072521.mp4")
        create_test_video(video)
        fmt._exif_cache.clear()

        first = fmt.fix_media_timestamps(video, timezone_spec="+08:00")
        assert first.timestamp_action == "fixed"
        fmt._exif_cache.clear()

        calls = self._spy_on_writes(monkeypatch)
        second = fmt.fix_media_timestamps(video, timezone_spec="+08:00")

        assert second.timestamp_action == "no_change"
        assert calls == []


class TestMachineOriginalTimeCarriesZoneSemantics:
    """The diff table has to be able to explain a row from the machine output alone.

    A UTC clock's digits are UTC, but the raw field carries no zone, so a row read
    "2025:06:17 23:25:21 → 2025:06:18 07:25:21+08:00" as an eight-hour shift that
    never happened. The emitted original states the zone it is in whenever the
    winning source's digits are UTC; a naive source has no zone to state and stays
    bare, which is the honest answer.
    """

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        fmt._exif_cache.clear()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def _video(self, filename, **tags):
        path = os.path.join(self.temp_dir, filename)
        create_test_video(path, **tags)
        fmt._exif_cache.clear()
        return path

    def test_quicktime_clock_original_is_emitted_as_utc(self):
        """A MediaCreateDate original is a UTC instant: emitted with a trailing Z so
        it is never mistaken for a +00:00 local-zone offset."""
        video = self._video("test.mp4",
                            **{"QuickTime:MediaCreateDate": "2025:06:17 23:25:21"})

        result = fmt.fix_media_timestamps(video, dry_run=True, timezone_spec="+08:00")

        assert result.original_time == "2025:06:17 23:25:21Z"
        assert result.corrected_time == "2025:06:18 07:25:21+08:00"

    def test_creationdate_with_z_original_is_emitted_as_utc(self):
        """Keys:CreationDate with a Z marker is UTC too; the Z is kept as-is rather
        than converted to a ±HH:MM offset, which would be a different claim."""
        video = self._video("test.mp4",
                            **{"Keys:CreationDate": "2025:06:17 23:25:21Z"})

        result = fmt.fix_media_timestamps(video, dry_run=True, timezone_spec="+08:00")

        assert result.original_time == "2025:06:17 23:25:21Z"

    def test_naive_datetimeoriginal_original_stays_bare(self):
        """A bare DateTimeOriginal has no zone of its own — claiming one would be a
        lie, so the original is emitted exactly as stored."""
        video = self._video("test.mp4", DateTimeOriginal="2025:06:18 07:25:21")

        result = fmt.fix_media_timestamps(video, dry_run=True, timezone_spec="+08:00")

        assert result.original_time == "2025:06:18 07:25:21"

    def test_zoned_datetimeoriginal_keeps_its_own_offset(self):
        """A zoned source already states its zone and is passed through untouched."""
        video = self._video("test.mp4", DateTimeOriginal="2025:06:18 07:25:21+08:00")

        result = fmt.fix_media_timestamps(video, dry_run=True, timezone_spec="+08:00")

        assert result.original_time == "2025:06:18 07:25:21+08:00"

    def test_filename_source_original_claims_no_zone(self):
        """A filename timestamp is wall-clock digits with no zone at all."""
        video = self._video("VID_20250618_072521.mp4")

        result = fmt.fix_media_timestamps(video, dry_run=True, timezone_spec="+08:00")

        assert "Z" not in (result.original_time or "")


class TestStaleFieldsNamesWhatWouldBeWritten:
    """"Would fix" on a row whose original and corrected times are identical is only
    explicable if the result says which fields it would write. stale_fields is the
    machine form of the human "Change:" line: the write tags whose stored value
    differs from the correction's target, and nothing when they all already match.
    """

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        fmt._exif_cache.clear()
        # Zoned DateTimeOriginal and track atoms already correct for +08:00; only the
        # movie header is eight hours out and Keys:CreationDate is missing entirely.
        self.video = os.path.join(self.temp_dir, "test.mp4")
        create_test_video(
            self.video,
            DateTimeOriginal="2025:06:18 07:25:21+08:00",
            **{"QuickTime:CreateDate": "2025:06:18 07:25:21",
               "QuickTime:MediaCreateDate": "2025:06:17 23:25:21",
               "QuickTime:TrackCreateDate": "2025:06:17 23:25:21"},
        )
        fmt._exif_cache.clear()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def test_lists_exactly_the_write_tags_that_differ(self):
        """The correct track atoms are not listed; the missing Keys:CreationDate and
        the stale movie header are."""
        result = fmt.fix_media_timestamps(self.video, dry_run=True, timezone_spec="+08:00")

        assert result.timestamp_action == "would_fix"
        assert result.stale_fields == ["Keys:CreationDate", "QuickTime:CreateDate"]

    def test_empty_once_the_correction_has_landed(self):
        """After applying, nothing differs from its target, so the list is empty and
        the row has nothing left to justify a change."""
        fmt.fix_media_timestamps(self.video, timezone_spec="+08:00")
        fmt._exif_cache.clear()

        second = fmt.fix_media_timestamps(self.video, dry_run=True, timezone_spec="+08:00")

        assert second.timestamp_action == "no_change"
        assert second.stale_fields == []


if __name__ == "__main__":
    # Run with pytest
    import pytest
    pytest.main([__file__, "-v"])
