#!/usr/bin/env python3
"""
Tests for lib/timestamp_source.py
Validates filename parsing, build_filename round-trips, and timestamp report generation.
"""

import os
import sys
import tempfile
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest

from conftest import create_test_video

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.timestamp_source import (
    parse_filename_timestamp,
    build_filename,
    read_timestamp_sources,
    extract_metadata_timezone,
    get_best_timestamp,
    read_exif_data,
    clear_exif_cache,
    TimestampReport,
)


class TestParseFilenameTimestamp:
    """Generic date pattern matching — prefix-agnostic."""

    def test_yyyymmdd_hhmmss_insta360(self):
        ts, pattern = parse_filename_timestamp("/path/VID_20250505_130334_00_001.mp4")
        assert ts == "2025:05:05 13:03:34"
        assert pattern == "YYYYMMDD_HHMMSS"

    def test_yyyymmdd_hhmmss_lrv(self):
        ts, pattern = parse_filename_timestamp("/path/LRV_20250505_130334_00_001.mp4")
        assert ts == "2025:05:05 13:03:34"
        assert pattern == "YYYYMMDD_HHMMSS"

    def test_yyyymmdd_hhmmss_img(self):
        ts, pattern = parse_filename_timestamp("/path/IMG_20250505_130334.jpg")
        assert ts == "2025:05:05 13:03:34"
        assert pattern == "YYYYMMDD_HHMMSS"

    def test_yyyymmddhhmmss_dji(self):
        ts, pattern = parse_filename_timestamp("/path/DJI_20250505130334_0001.mp4")
        assert ts == "2025:05:05 13:03:34"
        assert pattern == "YYYYMMDDHHMMSS"

    def test_yyyymmdd_hhmmss_prefix_agnostic_insv(self):
        ts, pattern = parse_filename_timestamp("/path/INSV_20250505_130334.insv")
        assert ts == "2025:05:05 13:03:34"
        assert pattern == "YYYYMMDD_HHMMSS"

    def test_yyyymmdd_hhmmss_prefix_agnostic_r360(self):
        ts, pattern = parse_filename_timestamp("/path/R360_20250505_130334.mp4")
        assert ts == "2025:05:05 13:03:34"
        assert pattern == "YYYYMMDD_HHMMSS"

    def test_screenshot_pattern(self):
        ts, pattern = parse_filename_timestamp("/path/Screenshot 2025-05-05 at 13.03.34.png")
        assert ts == "2025:05:05 13:03:34"
        assert pattern == "YYYY-MM-DD_at_HH.MM.SS"

    def test_yyyymmdd_date_only(self):
        ts, pattern = parse_filename_timestamp("/path/DSC_20250505_001.jpg")
        assert ts == "2025:05:05 00:00:00"
        assert pattern == "YYYYMMDD"

    def test_no_match_random(self):
        ts, pattern = parse_filename_timestamp("/path/random_file.mp4")
        assert ts is None
        assert pattern is None

    def test_no_match_invalid_date(self):
        """Month 13 should not match"""
        ts, pattern = parse_filename_timestamp("/path/VID_20251305_130334.mp4")
        assert ts is None

    def test_no_match_old_year(self):
        """Years before 2000 should not match"""
        ts, pattern = parse_filename_timestamp("/path/VID_19990505_130334.mp4")
        assert ts is None

    def test_most_specific_wins(self):
        """YYYYMMDD_HHMMSS should match before YYYYMMDD"""
        ts, pattern = parse_filename_timestamp("/path/VID_20250505_130334.mp4")
        assert pattern == "YYYYMMDD_HHMMSS"
        assert "13:03:34" in ts


class TestBuildFilename:
    """Reverse of parse — replace date in filename with corrected date."""

    def test_yyyymmdd_hhmmss_round_trip(self):
        corrected = datetime(2025, 6, 1, 14, 30, 0)
        result = build_filename("VID_20250505_130334_00_001.mp4", corrected)
        assert result == "VID_20250601_143000_00_001.mp4"

    def test_yyyymmddhhmmss_round_trip(self):
        corrected = datetime(2025, 6, 1, 14, 30, 0)
        result = build_filename("DJI_20250505130334_0001.mp4", corrected)
        assert result == "DJI_20250601143000_0001.mp4"

    def test_screenshot_round_trip(self):
        corrected = datetime(2025, 6, 1, 14, 30, 0)
        result = build_filename("Screenshot 2025-05-05 at 13.03.34.png", corrected)
        assert result == "Screenshot 2025-06-01 at 14.30.00.png"

    def test_yyyymmdd_round_trip(self):
        corrected = datetime(2025, 6, 1)
        result = build_filename("DSC_20250505_001.jpg", corrected)
        assert result == "DSC_20250601_001.jpg"

    def test_unparseable_returns_none(self):
        corrected = datetime(2025, 6, 1)
        result = build_filename("random_file.mp4", corrected)
        assert result is None

    def test_preserves_extension(self):
        corrected = datetime(2025, 6, 1, 14, 30, 0)
        result = build_filename("VID_20250505_130334.insv", corrected)
        assert result.endswith(".insv")

    def test_preserves_sequence_numbers(self):
        corrected = datetime(2025, 6, 1, 14, 30, 0)
        result = build_filename("VID_20250505_130334_00_003.mp4", corrected)
        assert result == "VID_20250601_143000_00_003.mp4"


class TestReadTimestampSources:
    """Unified analysis via read_timestamp_sources()."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        clear_exif_cache()

    def test_dto_with_timezone(self):
        video = os.path.join(self.temp_dir, "test.mp4")
        create_test_video(video, DateTimeOriginal="2025:06:18 07:25:21+08:00")

        report = read_timestamp_sources(video)
        assert report.metadata_date is not None
        assert report.metadata_date.hour == 7
        assert report.metadata_date.minute == 25
        assert report.metadata_tz == "+08:00"
        assert "DateTimeOriginal" in report.metadata_source

    def test_filename_only(self):
        video = os.path.join(self.temp_dir, "VID_20250618_072521.mp4")
        create_test_video(video)

        report = read_timestamp_sources(video, timezone_offset="+08:00")
        assert report.filename_parseable is True
        assert report.filename_date is not None
        assert report.filename_date.hour == 7
        assert report.filename_date.minute == 25
        assert report.filename_pattern == "YYYYMMDD_HHMMSS"

    def test_both_present(self):
        video = os.path.join(self.temp_dir, "VID_20250618_072521.mp4")
        create_test_video(video, DateTimeOriginal="2025:06:18 09:25:21+08:00")

        report = read_timestamp_sources(video)
        assert report.metadata_date is not None
        assert report.filename_parseable is True
        assert report.filename_date is not None

    def test_unparseable_filename(self):
        video = os.path.join(self.temp_dir, "test.mp4")
        create_test_video(video, DateTimeOriginal="2025:06:18 07:25:21+08:00")

        report = read_timestamp_sources(video)
        assert report.filename_parseable is False
        assert report.filename_date is None
        assert report.filename_pattern is None


class TestExtractMetadataTimezone:
    """Preserved behavior from original extract_metadata_timezone()."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        clear_exif_cache()

    def test_from_datetimeoriginal(self):
        video = os.path.join(self.temp_dir, "test.mp4")
        create_test_video(video, DateTimeOriginal="2025:06:18 07:25:21+08:00")

        result = extract_metadata_timezone(video)
        assert result == "+08:00"

    def test_none_when_no_timezone(self):
        video = os.path.join(self.temp_dir, "test.mp4")
        create_test_video(video)

        result = extract_metadata_timezone(video)
        assert result is None


class TestGetBestTimestamp:
    """Preserved priority behavior."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        clear_exif_cache()

    def test_dto_with_tz_is_priority_1(self):
        video = os.path.join(self.temp_dir, "test.mp4")
        create_test_video(video, DateTimeOriginal="2025:06:18 07:25:21+08:00")

        ts, source = get_best_timestamp(video)
        assert ts == "2025:06:18 07:25:21"
        assert "DateTimeOriginal" in source

    def test_filename_for_vid_prefix(self):
        video = os.path.join(self.temp_dir, "VID_20250618_072521.mp4")
        create_test_video(video)

        ts, source = get_best_timestamp(video, timezone_offset="+08:00")
        assert ts == "2025:06:18 07:25:21"
        assert "filename" in source


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
