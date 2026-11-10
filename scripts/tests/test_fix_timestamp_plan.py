"""
A timestamp correction is planned before anything is said or written:
plan_correction turns what a file holds into the time it should carry, the
fields that must change and the one write that changes them. These tests run
that plan in-process over a fake metadata client, so the ranking and timezone
rules are checked without exiftool; apply_correction is checked to send at most
one write, and none on a dry run.

The rules themselves are in docs/timestamp-fields.md.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from lib import fix_media_timestamp
from lib.fix_media_timestamp import (
    NO_TIMESTAMP, REFUSED_WITHOUT_FORCE, ZONE_NEEDED, CorrectionOptions, apply_correction,
    plan_correction, read_current,
)
from lib.timestamp_source import TimestampSource

CLIP = "/cards/C0001.MP4"
NAMED_CLIP = "/cards/VID_20251005_100000_00_001.mp4"
MOVIE_HEADER_UTC = {
    "MovieHeaderCreateDate": "2025:10:05 01:00:00",
    "MediaCreateDate": "2025:10:05 01:00:00",
    "TrackCreateDate": "2025:10:05 01:00:00",
}


def _plan(fake_metadata, path, tags, **options):
    """The plan for a file holding tags, with birth time out of the picture so
    the plan is the same on every platform."""
    fake_metadata.files[path] = tags
    opts = CorrectionOptions(**options)
    current = replace(read_current(path, opts), birth_time_tracked=False)
    return plan_correction(current, opts)


def _zone(hours: int) -> timezone:
    return timezone(timedelta(hours=hours))


class TestRanking:

    def test_a_zoned_datetime_original_outranks_the_movie_header(self, fake_metadata):
        """Actual: the zoned tag's time, read as it is
        Expected: a camera-written zone is the best evidence there is"""
        plan = _plan(fake_metadata, CLIP,
                     {**MOVIE_HEADER_UTC, "DateTimeOriginal": "2025:10:05 10:30:00+08:00"},
                     timezone_spec="+08:00")

        assert plan.current.data["timestamp_source"] is TimestampSource.DATETIME_ORIGINAL_ZONED
        assert plan.corrected == datetime(2025, 10, 5, 10, 30, tzinfo=_zone(8))
        assert not plan.requires_force_timezone and plan.problem is None

    def test_a_utc_movie_header_is_expressed_in_the_declared_zone(self, fake_metadata):
        """Actual: 01:00 UTC becomes 10:00+09:00, the same instant
        Expected: --timezone relabels a UTC clock, it never moves it"""
        plan = _plan(fake_metadata, CLIP, MOVIE_HEADER_UTC, timezone_spec="+0900")

        assert plan.current.data["timestamp_source"].is_utc
        assert plan.corrected_str == "2025:10:05 10:00:00+09:00"
        assert plan.corrected == plan.original
        assert plan.write_datetime_original

    def test_a_filename_alone_gives_the_time_in_the_declared_zone(self, fake_metadata):
        """Actual: the filename's digits with --timezone's offset, every field added
        Expected: a file with no clock fields only gains what it never had"""
        plan = _plan(fake_metadata, NAMED_CLIP, {}, timezone_spec="-05:00", apply=False)

        assert plan.current.data["timestamp_source"] is TimestampSource.FILENAME
        assert plan.corrected_str == "2025:10:05 10:00:00-05:00"
        assert plan.only_adds_fields
        assert apply_correction(plan).timestamp_action == "would_add"

    def test_infer_from_filename_overrides_a_stored_datetime_original(self, fake_metadata):
        """Actual: the filename wins and DateTimeOriginal is rewritten
        Expected: --infer-from-filename makes the filename the source of truth"""
        plan = _plan(fake_metadata, NAMED_CLIP,
                     {"DateTimeOriginal": "2024:01:01 00:00:00+09:00"},
                     timezone_spec="-05:00", infer_from_filename=True)

        assert plan.current.data["timestamp_source"] is TimestampSource.FILENAME_INFERRED
        assert plan.corrected_str == "2025:10:05 10:00:00-05:00"
        assert plan.write_datetime_original
        assert "DateTimeOriginal" in plan.changes["stale_clock_fields"]


class TestTimezoneGate:
    """Relabelling a file that already carries a zone needs --force-timezone to apply."""

    TAGS = {**MOVIE_HEADER_UTC, "DateTimeOriginal": "2025:10:05 09:00:00+08:00"}

    def test_a_dry_run_previews_the_relabel_and_flags_it(self, fake_metadata):
        plan = _plan(fake_metadata, CLIP, self.TAGS, timezone_spec="+09:00", apply=False)

        assert plan.requires_force_timezone and plan.problem is None
        assert plan.corrected == datetime(2025, 10, 5, 10, 0, tzinfo=_zone(9))
        assert apply_correction(plan).requires_force_timezone

    def test_applying_without_the_flag_is_refused_without_a_write(self, fake_metadata):
        plan = _plan(fake_metadata, CLIP, self.TAGS, timezone_spec="+09:00", apply=True)

        result = apply_correction(plan)

        assert plan.problem == REFUSED_WITHOUT_FORCE
        assert (result.timestamp_action, result.requires_force_timezone) == ("error", True)
        assert fake_metadata.writes == []

    def test_the_flag_confirms_the_relabel_into_the_stored_tag(self, fake_metadata):
        plan = _plan(fake_metadata, CLIP, self.TAGS, timezone_spec="+09:00",
                     apply=True, force_timezone=True)

        assert not plan.requires_force_timezone
        assert plan.changes["clock_targets"]["DateTimeOriginal"] == "2025:10:05 10:00:00+09:00"
        assert apply_correction(plan).timestamp_action == "fixed"

    def test_the_same_zone_needs_no_flag(self, fake_metadata):
        plan = _plan(fake_metadata, CLIP, self.TAGS, timezone_spec="+08:00", apply=True)
        assert not plan.requires_force_timezone and plan.problem is None


class TestTimeOffset:

    def test_an_offset_moves_the_time_and_keeps_the_original(self, fake_metadata):
        """Actual: corrected is an hour earlier than original, mode is time
        Expected: only --time-offset moves the actual time"""
        plan = _plan(fake_metadata, CLIP, MOVIE_HEADER_UTC, timezone_spec="+09:00",
                     time_offset_seconds=-3600)

        assert plan.original is not None and plan.corrected is not None
        assert plan.corrected - plan.original == timedelta(hours=-1)
        assert plan.corrected_str == "2025:10:05 09:00:00+09:00"
        assert plan.correction_mode == "time" and not plan.only_adds_fields
        result = plan.result("would_fix")
        assert (result.time_offset_seconds, result.time_offset_display) == (-3600, "-0d 1h 0m 0s")

    def test_a_zero_offset_is_no_offset(self, fake_metadata):
        plan = _plan(fake_metadata, CLIP, MOVIE_HEADER_UTC, timezone_spec="+09:00",
                     time_offset_seconds=0)
        assert plan.correction_mode == "timezone" and plan.corrected == plan.original


class TestNothingToCorrect:

    def test_a_create_date_without_a_zone_asks_for_one(self, fake_metadata):
        """A still's bare CreateDate is local time with no zone: nothing to plan from."""
        plan = _plan(fake_metadata, "/cards/IMG.JPG", {"CreateDate": "2025:10:05 10:00:00"})

        result = apply_correction(plan)

        assert plan.problem == ZONE_NEEDED
        assert (result.timestamp_action, result.original_time) == ("error", "2025:10:05 10:00:00")

    def test_a_file_with_no_time_at_all_is_an_error(self, fake_metadata, monkeypatch):
        monkeypatch.setattr(fix_media_timestamp, "get_best_timestamp",
                            lambda *_: (None, TimestampSource.NONE))
        plan = _plan(fake_metadata, CLIP, {}, timezone_spec="+09:00")

        assert plan.problem == NO_TIMESTAMP
        assert apply_correction(plan).timestamp_action == "error"


class TestOneWrite:

    def test_a_dry_run_writes_nothing(self, fake_metadata):
        plan = _plan(fake_metadata, CLIP, MOVIE_HEADER_UTC, timezone_spec="+09:00", apply=False)

        assert apply_correction(plan).timestamp_action == "would_add"
        assert fake_metadata.writes == []

    def test_an_apply_sends_provenance_clock_fields_and_other_steps_fields_in_one_write(
            self, fake_metadata):
        """Actual: one write holding the recovery record, every clock target and tag's
        camera fields
        Expected: each file is rewritten once (docs/testing.md, pipeline cost)"""
        plan = _plan(fake_metadata, CLIP, MOVIE_HEADER_UTC, timezone_spec="+09:00", apply=True,
                     extra_write_fields={"Make": "Test"})

        result = apply_correction(plan)

        assert result.timestamp_action == "added"
        assert len(fake_metadata.writes) == 1
        path, args = fake_metadata.writes[0]
        assert path == CLIP
        assert "-XMP-xmpMM:PreservedFileName=C0001.MP4" in args
        assert "-DateTimeOriginal=2025:10:05 10:00:00+09:00" in args
        assert "-QuickTime:TrackCreateDate=2025:10:05 01:00:00" in args
        assert args[-1] == "-Make=Test"

    def test_other_steps_fields_are_written_when_the_time_is_already_right(self, fake_metadata):
        """Actual: no_change, yet tag's fields still went out in one write
        Expected: the pipeline relies on this write for the camera fields"""
        correct = {**MOVIE_HEADER_UTC,
                   "DateTimeOriginal": "2025:10:05 10:00:00+09:00",
                   "OffsetTimeOriginal": "+09:00",
                   "CreationDate": "2025:10:05 10:00:00+09:00",
                   "PreservedFileName": "C0001.MP4"}
        plan = _plan(fake_metadata, CLIP, correct, timezone_spec="+09:00", apply=True,
                     extra_write_fields={"Model": "Camera"})

        result = apply_correction(plan)

        assert result.timestamp_action == "no_change"
        assert fake_metadata.writes == [(CLIP, ["-Model=Camera"])]

    @pytest.mark.parametrize("apply", [True, False])
    def test_nothing_to_change_and_nothing_to_carry_writes_nothing(self, fake_metadata, apply):
        correct = {**MOVIE_HEADER_UTC,
                   "DateTimeOriginal": "2025:10:05 10:00:00+09:00",
                   "OffsetTimeOriginal": "+09:00",
                   "CreationDate": "2025:10:05 10:00:00+09:00"}
        plan = _plan(fake_metadata, CLIP, correct, timezone_spec="+09:00", apply=apply)

        assert apply_correction(plan).timestamp_action == "no_change"
        assert fake_metadata.writes == []
