"""
The timezone pre-flight decides, before any file is touched, whether a batch's
embedded zones stop the run. preflight_timezones is the pure decision over each
file's embedded and expected zone; read_file_zones is the read that feeds it.
These tests pin the decision without starting exiftool: a wrong answer either
relabels a whole batch to the wrong zone or refuses one that was fine.
"""

from __future__ import annotations

from pathlib import Path

from lib.pipeline.preflight import (
    MIXED_TIMEZONES, PROVIDED_MISMATCH, FileZone, TimezoneConflict, preflight_timezones,
    read_file_zones,
)


class TestPreflightTimezones:

    def test_a_batch_without_embedded_zones_has_no_conflict(self):
        assert preflight_timezones([]) is None

    def test_one_embedded_zone_and_no_timezone_given_has_no_conflict(self):
        zones = [FileZone("a.mp4", "+0900"), FileZone("b.mp4", "+0900")]
        assert preflight_timezones(zones) is None

    def test_two_embedded_zones_are_mixed_grouped_in_file_order(self):
        """Actual: a mixed conflict grouping each file under its zone
        Expected: the event lists files in the order they were found"""
        zones = [FileZone("b.mp4", "+0900"), FileZone("a.mp4", "+0800"), FileZone("c.mp4", "+0900")]

        conflict = preflight_timezones(zones)

        assert conflict == TimezoneConflict(
            MIXED_TIMEZONES, {"+0900": ["b.mp4", "c.mp4"], "+0800": ["a.mp4"]}, {})
        assert list(conflict.file_timezones) == ["+0900", "+0800"]

    def test_allowing_mixed_zones_still_checks_them_against_the_given_timezone(self):
        """Actual: with --allow-mixed-timezones, the file --timezone disagrees with is
        a provided mismatch
        Expected: allowing a mix is not forcing a relabel"""
        zones = [FileZone("a.mp4", "+0900", expected="+0900"),
                 FileZone("b.mp4", "+0800", expected="+0900")]

        conflict = preflight_timezones(zones, allow_mixed=True)

        assert conflict == TimezoneConflict(
            PROVIDED_MISMATCH, {"+0900": ["a.mp4"], "+0800": ["b.mp4"]}, {"+0800": ["b.mp4"]})

    def test_given_timezone_matching_every_file_has_no_conflict(self):
        zones = [FileZone("a.mp4", "+0900", expected="+0900")]
        assert preflight_timezones(zones) is None

    def test_given_timezone_differing_from_the_embedded_one_is_a_provided_mismatch(self):
        zones = [FileZone("a.mp4", "+0800", expected="+0900")]

        conflict = preflight_timezones(zones)

        assert conflict == TimezoneConflict(
            PROVIDED_MISMATCH, {"+0800": ["a.mp4"]}, {"+0800": ["a.mp4"]})

    def test_force_timezone_accepts_the_relabel(self):
        zones = [FileZone("a.mp4", "+0800", expected="+0900")]
        assert preflight_timezones(zones, force=True) is None

    def test_mixed_zones_win_over_a_provided_mismatch(self):
        """Actual: the mixed conflict is reported, not the mismatch
        Expected: the first thing to fix is the mix"""
        zones = [FileZone("a.mp4", "+0900", expected="+0900"),
                 FileZone("b.mp4", "+0800", expected="+0900")]
        assert preflight_timezones(zones).kind == MIXED_TIMEZONES


class TestReadFileZones:

    def test_a_zone_name_resolves_per_file_across_a_dst_change(self, fake_metadata):
        """A run spanning a DST changeover compares each file with the offset its
        zone had when that file was shot.

        Actual: the January file expects +1300 and the July file +1200
        Expected: Pacific/Auckland is not one fixed offset
        """
        summer, winter = Path("/cards/summer.mp4"), Path("/cards/winter.mp4")
        fake_metadata.files[str(summer)] = {"DateTimeOriginal": "2025:01:10 10:00:00+13:00"}
        fake_metadata.files[str(winter)] = {"DateTimeOriginal": "2025:07:10 10:00:00+12:00"}

        zones = read_file_zones([summer, winter], "Pacific/Auckland")

        assert zones == [FileZone("summer.mp4", "+1300", "+1300"),
                         FileZone("winter.mp4", "+1200", "+1200")]
        assert fake_metadata.writes == []

    def test_files_without_an_embedded_zone_are_left_out(self, fake_metadata):
        bare = Path("/cards/bare.mp4")
        fake_metadata.files[str(bare)] = {"MediaCreateDate": "2025:10:05 01:00:00"}

        assert read_file_zones([bare], "+0900") == []

    def test_without_a_timezone_nothing_is_expected(self, fake_metadata):
        clip = Path("/cards/clip.mp4")
        fake_metadata.files[str(clip)] = {"CreationDate": "2025:10:05 10:00:00+09:00"}

        assert read_file_zones([clip], None) == [FileZone("clip.mp4", "+0900", None)]
