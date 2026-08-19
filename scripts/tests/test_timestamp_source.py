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

from conftest import create_test_photo, create_test_video

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.metadata import metadata_service as exiftool
from lib.timestamp_source import (
    parse_filename_timestamp,
    build_filename,
    read_timestamp_sources,
    extract_metadata_timezone,
    get_best_timestamp,
    read_exif_data,
    clear_exif_cache,
    is_zone_name,
    resolve_timezone_offset,
    resolve_file_timezone_offset,
    camera_zone_offset_for_file,
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

    def test_bare_creationdate_ranks_with_bare_datetimeoriginal(self):
        """A Keys:CreationDate with no zone suffix and no Z is a naive source, ranked
        at the same tier as a bare DateTimeOriginal — not ignored.

        Written via the raw '#' form: exiftool's CreationDate PrintConvInv otherwise
        auto-appends the writing machine's local timezone to a bare value, which
        would defeat the point of this fixture.
        """
        video = os.path.join(self.temp_dir, "test.mp4")
        create_test_video(video, **{"Keys:CreationDate#": "2025:06:18 07:25:21"})

        ts, source = get_best_timestamp(video, timezone_offset="+08:00")
        assert ts == "2025:06:18 07:25:21"
        assert source == "CreationDate"

    def test_bare_creationdate_loses_to_zoned_datetimeoriginal(self):
        """A higher-ranked source (zoned DateTimeOriginal, priority 1) still wins over
        a bare Keys:CreationDate present on the same file."""
        video = os.path.join(self.temp_dir, "test.mp4")
        create_test_video(
            video,
            **{
                "DateTimeOriginal": "2025:06:18 09:25:21+08:00",
                "Keys:CreationDate#": "2025:06:18 07:00:00",
            },
        )

        ts, source = get_best_timestamp(video, timezone_offset="+08:00")
        assert ts == "2025:06:18 09:25:21"
        assert source == "DateTimeOriginal with timezone"


class TestQuickTimeInstantVersusFilename:
    """A camera filename records the digits the camera displayed, with no zone. A
    QuickTime date records an instant. Where the two contradict each other the instant
    wins, but only where the file itself shows the QuickTime date to be one — a legal
    zone offset from the filename, which is -12:00 to +14:00 in quarter-hour steps.
    """

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        clear_exif_cache()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _video(self, name, media_create_date=None):
        path = os.path.join(self.temp_dir, name)
        if media_create_date:
            create_test_video(path, **{"QuickTime:MediaCreateDate": media_create_date})
        else:
            create_test_video(path)
        return path

    def test_instant_outranks_camera_filename(self):
        """Camera left on Japan time while shooting in New Zealand."""
        video = self._video("VID_20260104_033532_00_001.mp4", "2026:01:03 18:35:32")

        ts, source = get_best_timestamp(video, timezone_offset="+13:00")

        assert ts == "2026:01:03 18:35:32"
        assert source == "MediaCreateDate"

    def test_filename_wins_without_a_declared_timezone(self):
        """An instant cannot be labelled without a zone to label it in."""
        video = self._video("VID_20260104_033532_00_001.mp4", "2026:01:03 18:35:32")

        ts, source = get_best_timestamp(video)

        assert ts == "2026:01:04 03:35:32"
        assert source == "filename"

    def test_filename_wins_when_the_clock_is_broken(self):
        """A battery-reset camera: years from any legal offset, so not an instant."""
        video = self._video("VID_20250505_120334_00_029.mp4", "2018:11:24 17:03:34")

        ts, source = get_best_timestamp(video, timezone_offset="+01:00")

        assert ts == "2025:05:05 12:03:34"
        assert source == "filename"

    def test_filename_wins_when_the_quicktime_date_matches_it(self):
        """Zero delta cannot separate a UTC+0 camera from one writing local time."""
        video = self._video("VID_20250618_072521_00_001.mp4", "2025:06:18 07:25:21")

        _, source = get_best_timestamp(video, timezone_offset="+08:00")

        assert source == "filename"

    def test_filename_wins_when_the_quicktime_date_is_zeroed(self):
        video = self._video("VID_20250618_072521_00_001.mp4")

        _, source = get_best_timestamp(video, timezone_offset="+08:00")

        assert source == "filename"

    def test_offset_at_the_legal_maximum_is_an_instant(self):
        """+14:00, the largest offset any zone uses."""
        video = self._video("VID_20250618_140000_00_001.mp4", "2025:06:18 00:00:00")

        _, source = get_best_timestamp(video, timezone_offset="+14:00")

        assert source == "MediaCreateDate"

    def test_offset_beyond_the_legal_maximum_is_not(self):
        video = self._video("VID_20250618_150000_00_001.mp4", "2025:06:18 00:00:00")

        _, source = get_best_timestamp(video, timezone_offset="+14:00")

        assert source == "filename"

    def test_offset_at_the_legal_minimum_is_an_instant(self):
        """-12:00, the filename twelve hours behind the instant."""
        video = self._video("VID_20250617_120000_00_001.mp4", "2025:06:18 00:00:00")

        _, source = get_best_timestamp(video, timezone_offset="-12:00")

        assert source == "MediaCreateDate"

    def test_offset_beyond_the_legal_minimum_is_not(self):
        video = self._video("VID_20250617_110000_00_001.mp4", "2025:06:18 00:00:00")

        _, source = get_best_timestamp(video, timezone_offset="-12:00")

        assert source == "filename"

    def test_quarter_hour_offset_is_an_instant(self):
        """Nepal is +05:45."""
        video = self._video("VID_20250618_054500_00_001.mp4", "2025:06:18 00:00:00")

        _, source = get_best_timestamp(video, timezone_offset="+05:45")

        assert source == "MediaCreateDate"

    def test_offset_off_the_quarter_hour_is_not(self):
        """9h07m is not an offset any zone uses."""
        video = self._video("VID_20260104_034232_00_001.mp4", "2026:01:03 18:35:32")

        _, source = get_best_timestamp(video, timezone_offset="+13:00")

        assert source == "filename"

    def test_a_file_with_no_filename_date_still_uses_the_quicktime_date(self):
        """Nothing to cross-check against, and nothing else to fall back to."""
        video = self._video("clip.mp4", "2026:01:03 18:35:32")

        ts, source = get_best_timestamp(video, timezone_offset="+13:00")

        assert ts == "2026:01:03 18:35:32"
        assert source == "MediaCreateDate"


class TestCameraZoneOffsetForFile:
    """The camera's own zone setting at shoot time, read independently of
    get_best_timestamp()'s priority chain — present whenever a filename timestamp and a
    usable QuickTime date coexist with a legal zone delta, regardless of which source
    the ranking picks.
    """

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        clear_exif_cache()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _video(self, name, media_create_date=None):
        path = os.path.join(self.temp_dir, name)
        if media_create_date:
            create_test_video(path, **{"QuickTime:MediaCreateDate": media_create_date})
        else:
            create_test_video(path)
        return path

    def test_present_when_the_quicktime_date_wins_the_priority_race(self):
        """Camera left on Japan time while shooting in New Zealand — QuickTime wins."""
        video = self._video("VID_20260104_033532_00_001.mp4", "2026:01:03 18:35:32")

        assert camera_zone_offset_for_file(video) == "+09:00"

    def test_present_when_the_filename_wins_the_priority_race(self):
        """No --timezone declared, so the filename wins get_best_timestamp() outright —
        the camera zone offset is still computable from the raw fields on disk."""
        video = self._video("VID_20260104_033532_00_001.mp4", "2026:01:03 18:35:32")

        assert camera_zone_offset_for_file(video) == "+09:00"

    def test_absent_without_a_quicktime_date(self):
        video = self._video("VID_20250505_130334_00_001.mp4")

        assert camera_zone_offset_for_file(video) is None

    def test_absent_without_a_filename_timestamp(self):
        video = self._video("clip.mp4", "2026:01:03 18:35:32")

        assert camera_zone_offset_for_file(video) is None

    def test_absent_when_the_delta_is_not_a_legal_zone_offset(self):
        """A battery-reset camera: years from any legal offset."""
        video = self._video("VID_20250505_120334_00_029.mp4", "2018:11:24 17:03:34")

        assert camera_zone_offset_for_file(video) is None


class TestResolveTimezoneOffset:
    """A zone name resolves against the timestamp, not against today."""

    def test_fixed_offset_passes_through(self):
        assert resolve_timezone_offset("+0900", "2025:08:15 10:00:00") == "+09:00"
        assert resolve_timezone_offset("-0500", "2025:08:15 10:00:00") == "-05:00"

    def test_zone_without_dst_is_stable(self):
        assert resolve_timezone_offset("Asia/Tokyo", "2025:01:15 10:00:00") == "+09:00"
        assert resolve_timezone_offset("Asia/Tokyo", "2025:07:15 10:00:00") == "+09:00"

    def test_zone_follows_dst_of_the_shooting_date(self):
        assert resolve_timezone_offset("Pacific/Auckland", "2025:01:15 10:00:00") == "+13:00"
        assert resolve_timezone_offset("Pacific/Auckland", "2025:07:15 10:00:00") == "+12:00"

    def test_utc_source_converts_before_resolving(self):
        """A UTC timestamp is converted into the zone, not read as local time."""
        assert resolve_timezone_offset(
            "Pacific/Auckland", "2025:07:14 22:00:00", timestamp_is_utc=True
        ) == "+12:00"

    def test_unknown_zone_rejected(self):
        with pytest.raises(ValueError, match="Unknown timezone"):
            resolve_timezone_offset("Pacific/Atlantis", "2025:07:15 10:00:00")

    def test_no_spec_resolves_to_nothing(self):
        assert resolve_timezone_offset(None, "2025:07:15 10:00:00") is None

    def test_is_zone_name(self):
        assert is_zone_name("Pacific/Auckland") is True
        assert is_zone_name("+0900") is False
        assert is_zone_name("+09:00") is False
        assert is_zone_name("") is False


class TestResolveFileTimezoneOffset:
    """Each file resolves against its own timestamp."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        clear_exif_cache()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_files_either_side_of_a_changeover_differ(self):
        """NZ moved to standard time on 2025-04-06 — one run, two offsets."""
        summer = os.path.join(self.temp_dir, "VID_20250315_100000.mp4")
        winter = os.path.join(self.temp_dir, "VID_20250715_100000.mp4")
        create_test_video(summer)
        create_test_video(winter)

        assert resolve_file_timezone_offset(summer, "Pacific/Auckland") == "+13:00"
        assert resolve_file_timezone_offset(winter, "Pacific/Auckland") == "+12:00"

    def test_fixed_offset_applies_to_every_file(self):
        video = os.path.join(self.temp_dir, "VID_20250315_100000.mp4")
        create_test_video(video)

        assert resolve_file_timezone_offset(video, "+0900") == "+09:00"

    def test_no_spec_resolves_to_nothing(self):
        video = os.path.join(self.temp_dir, "VID_20250315_100000.mp4")
        create_test_video(video)

        assert resolve_file_timezone_offset(video, None) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestOffsetTimeOriginalCompletesBareDateTimeOriginal:
    """Binary EXIF DateTimeOriginal is exactly 19 characters, so OffsetTimeOriginal is the
    only place a still camera can record the zone its digits belong to. A still carrying
    both must therefore rank as a zoned source, not as a naive bare-DTO."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        clear_exif_cache()

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        clear_exif_cache()

    def test_bare_dto_plus_offset_reads_back_as_a_zoned_value(self):
        """A still whose zone lives in OffsetTimeOriginal presents one zoned
        DateTimeOriginal to every consumer of the shared EXIF read."""
        photo = os.path.join(self.tmpdir, "IMG_0001.jpg")
        create_test_photo(photo,
                          DateTimeOriginal="2025:06:18 07:25:21",
                          OffsetTimeOriginal="+08:00")

        assert read_exif_data(photo)["DateTimeOriginal"] == "2025:06:18 07:25:21+08:00"

    def test_completed_dto_wins_priority_one_as_a_zoned_source(self):
        """The completed value ranks at the zoned-DateTimeOriginal tier, beating the
        filename digits that would otherwise have won for this name."""
        photo = os.path.join(self.tmpdir, "IMG_20250101_010101.jpg")
        create_test_photo(photo,
                          DateTimeOriginal="2025:06:18 07:25:21",
                          OffsetTimeOriginal="+08:00")

        timestamp, source = get_best_timestamp(photo)
        assert source == "DateTimeOriginal with timezone"
        assert timestamp == "2025:06:18 07:25:21"

    def test_offset_time_original_supplies_the_metadata_timezone(self):
        """The zone a still recorded separately is the zone jetlag reports for it."""
        photo = os.path.join(self.tmpdir, "IMG_0002.jpg")
        create_test_photo(photo,
                          DateTimeOriginal="2025:06:18 07:25:21",
                          OffsetTimeOriginal="-05:00")

        assert extract_metadata_timezone(photo) == "-05:00"

    def test_bare_dto_without_offset_stays_naive(self):
        """Behaviour is unchanged for a still that never recorded a zone: it still
        ranks at the naive bare-DateTimeOriginal tier."""
        photo = os.path.join(self.tmpdir, "IMG_0003.jpg")
        create_test_photo(photo, DateTimeOriginal="2025:06:18 07:25:21")

        assert read_exif_data(photo)["DateTimeOriginal"] == "2025:06:18 07:25:21"
        timestamp, source = get_best_timestamp(photo)
        assert source == "DateTimeOriginal"
        assert timestamp == "2025:06:18 07:25:21"
        assert extract_metadata_timezone(photo) is None

    def test_malformed_offset_is_ignored(self):
        """A zone that is not a legal offset cannot silently corrupt the timestamp —
        the file falls back to ranking naive."""
        photo = os.path.join(self.tmpdir, "IMG_0004.jpg")
        create_test_photo(photo, DateTimeOriginal="2025:06:18 07:25:21")
        exiftool.write_tags(photo, ["-EXIF:OffsetTimeOriginal=garbage"])
        clear_exif_cache()

        assert read_exif_data(photo)["DateTimeOriginal"] == "2025:06:18 07:25:21"
        assert get_best_timestamp(photo)[1] == "DateTimeOriginal"

    def test_already_zoned_dto_is_left_untouched(self):
        """A value that already carries its own zone is never rewritten."""
        video = os.path.join(self.tmpdir, "VID_0005.mp4")
        create_test_video(video, DateTimeOriginal="2025:06:18 07:25:21+08:00")

        assert read_exif_data(video)["DateTimeOriginal"] == "2025:06:18 07:25:21+08:00"


class TestExiftoolStillWritePathForZonedDateTimeOriginal:
    """Pins the documented write-path fact in docs/timestamp-fields.md: exiftool does NOT
    split a zoned DateTimeOriginal into OffsetTimeOriginal when the target is a still —
    the 19-char binary EXIF field takes the digits and the zone is silently discarded."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        clear_exif_cache()

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        clear_exif_cache()

    def test_writing_a_zoned_dto_to_a_still_drops_the_zone(self):
        photo = os.path.join(self.tmpdir, "IMG_0006.jpg")
        create_test_photo(photo)

        exiftool.write_tags(photo, ["-DateTimeOriginal=2025:06:18 07:25:21+08:00"])

        raw = exiftool.read_tags(photo, ["EXIF:DateTimeOriginal",
                                         "EXIF:OffsetTimeOriginal"])
        assert raw.get("DateTimeOriginal") == "2025:06:18 07:25:21"
        assert "OffsetTimeOriginal" not in raw
