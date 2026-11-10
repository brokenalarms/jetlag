"""
The timezone pre-flight decides, before any file is touched, whether a batch's
embedded zones stop the run. preflight_timezones is the pure decision over each
file's embedded and expected zone; read_file_zones is the read that feeds it.
These tests pin the decision without starting exiftool: a wrong answer either
relabels a whole batch to the wrong zone or refuses one that was fine.

The end-to-end tests below them cover the other batch checks a run meets
before its first file: protected source files and the profile's camera.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

from helpers.media import create_test_video as _create_video_raw
from lib.media_pipeline.preflight import (
    MIXED_TIMEZONES, PROVIDED_MISMATCH, FileZone, TimezoneConflict, preflight_timezones,
    read_file_zones,
)
from helpers.pipeline import create_test_video, run_in_process, run_pipeline
from helpers.pipeline_schema import validate_event


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



@pytest.mark.skipif(not hasattr(os, "chflags"), reason="BSD file flags only")
class TestProtectedSources:
    """A source file carrying the user-immutable flag — what a camera's "Protect"
    becomes on macOS — cannot be imported as it is: every stage rewrites or moves
    its staged copy, and a lock carried onto that copy fails each of them with
    EPERM. Importing it means its copy in the library comes out unprotected, so
    an apply asks first: the batch reports the protected files as one
    protected_sources event, and only --unlock-protected lets the apply proceed.
    The source itself keeps its lock either way.
    """

    VIDEO = "VID_20251005_100000_00_001.mp4"

    @pytest.fixture
    def locked_source(self, temp_workspace):
        source = temp_workspace["source"] / self.VIDEO
        create_test_video(source)
        os.chflags(source, stat.UF_IMMUTABLE)
        yield source
        for path in temp_workspace["root"].rglob("*"):
            os.chflags(path, 0)

    def _run(self, workspace, profile, *extra):
        return run_pipeline([
            "--profile", profile,
            "--source", str(workspace["source"]),
            "--target", str(workspace["target"]),
            "--extensions", ".mp4", ".mov",
            "--timezone", "+0900",
            "--group", "Test",
            *extra,
        ])

    def _events(self, stdout: str) -> list[dict]:
        events = [json.loads(line) for line in stdout.strip().split("\n") if line.strip()]
        for event in events:
            validate_event(event)
        return events

    def _protected_events(self, events):
        return [e for e in events if e["event"] == "protected_sources"]

    def test_apply_without_assent_refuses_before_touching_anything(
            self, temp_workspace, test_profile, locked_source):
        """Actual: the run exits non-zero having reported the protected file,
        with nothing organized
        Expected: an apply never silently drops a protection the user set
        """
        result = self._run(temp_workspace, test_profile, "--apply")

        events = self._events(result.stdout)
        assert result.returncode != 0, \
            f"Actual: {result.output}, Expected: the apply refused"
        assert [e["files"] for e in self._protected_events(events)] == [[self.VIDEO]], \
            f"Actual: {events}, Expected: one protected_sources naming {self.VIDEO}"
        assert [e for e in events if e["event"] == "pipeline_file"] == [], \
            "Actual: files were processed, Expected: refused before the first file"
        assert sorted(temp_workspace["target"].rglob("*.mp4")) == [], \
            "Actual: a file reached the target, Expected: nothing organized"

    def test_apply_with_assent_imports_an_unlocked_copy(
            self, temp_workspace, test_profile, locked_source):
        """Actual: the organized file exists unlocked, the staging directory is
        empty of it, and the source is still locked
        Expected: a protected photo on the card no longer stops the import with
        "Operation not permitted" once the user has agreed to it
        """
        result = self._run(temp_workspace, test_profile, "--apply", "--unlock-protected")

        assert result.returncode == 0, f"Actual: {result.output}, Expected: a clean run"
        organized = sorted(temp_workspace["target"].rglob("*.mp4"))
        assert len(organized) == 1, f"Actual: {organized}, Expected: one organized file"
        assert not os.stat(organized[0]).st_flags & stat.UF_IMMUTABLE, \
            "Actual: the organized file is locked, Expected: unlocked"
        assert os.stat(locked_source).st_flags & stat.UF_IMMUTABLE, \
            "Actual: the source lost its lock, Expected: source untouched"

    def test_dry_run_reports_protected_files_and_previews_anyway(
            self, temp_workspace, test_profile, locked_source):
        """Actual: protected_sources is reported and every file is still previewed
        Expected: the preview tells the user what the apply will ask about
        """
        result = self._run(temp_workspace, test_profile)

        events = self._events(result.stdout)
        assert result.returncode == 0, f"Actual: {result.output}, Expected: a full preview"
        assert [e["files"] for e in self._protected_events(events)] == [[self.VIDEO]], \
            f"Actual: {events}, Expected: one protected_sources naming {self.VIDEO}"
        previewed = [e for e in events if e["event"] == "pipeline_result"]
        assert len(previewed) == 1, f"Actual: {previewed}, Expected: the file previewed"

    def test_unprotected_batch_reports_nothing(self, temp_workspace, test_profile):
        """Actual: no protected_sources event for a batch with no locked files
        Expected: the app has nothing to ask about on an ordinary import
        """
        create_test_video(temp_workspace["source"] / self.VIDEO)

        result = self._run(temp_workspace, test_profile, "--apply")

        assert result.returncode == 0, f"Actual: {result.output}, Expected: a clean run"
        assert self._protected_events(self._events(result.stdout)) == []


class TestSourceCameraIsCheckedAgainstTheProfile:
    """Every source file is held to the profile's camera before anything runs.

    A file the camera says was shot on another body means the profile was picked
    for the wrong camera — the sony-a7iv-photo profile once relabelled 143 A7V
    stills. The batch reports such files as one camera_mismatch event; a dry run
    previews anyway, an apply refuses without --allow-camera-mismatch, and the
    file's own camera fields are never overwritten. A profile with no camera —
    for media that records none — is not checked.
    """

    VIDEO = "VID_20251005_100000_00_001.mp4"

    def _run(self, workspace, profile, *extra):
        return run_in_process([
            "--profile", profile,
            "--source", str(workspace["source"]),
            "--target", str(workspace["target"]),
            "--extensions", ".mp4", ".mov",
            "--timezone", "+0900",
            "--group", "Test",
            *extra,
        ])

    def _events(self, stdout: str) -> list[dict]:
        events = [json.loads(line) for line in stdout.strip().split("\n") if line.strip()]
        for event in events:
            validate_event(event)
        return events

    def _video(self, workspace, **camera):
        _create_video_raw(workspace["source"] / self.VIDEO,
                          MediaCreateDate="2025:10:05 01:00:00",
                          CreateDate="2025:10:05 01:00:00", **camera)

    def _of(self, events, kind):
        return [e for e in events if e["event"] == kind]

    def _camera(self, path) -> tuple:
        out = subprocess.run(["exiftool", "-s3", "-Make", "-Model", str(path)],
                             capture_output=True, text=True).stdout.split("\n")
        return out[0], out[1]

    def _set_profile_exif(self, exif):
        path = os.environ["JETLAG_PROFILES_FILE"]
        with open(path) as f:
            profiles = yaml.safe_load(f)
        profiles["profiles"]["_test"]["exif"] = exif
        with open(path, "w") as f:
            yaml.dump(profiles, f, default_flow_style=False, sort_keys=False)

    def test_apply_refuses_a_file_from_another_camera(self, temp_workspace, test_profile):
        """Actual: the apply exits non-zero naming the file, with nothing organized
        Expected: the wrong profile never imports a batch unasked
        """
        self._video(temp_workspace, Make="Test", Model="Other Body")

        result = self._run(temp_workspace, test_profile, "--apply")

        events = self._events(result.stdout)
        mismatch = self._of(events, "camera_mismatch")
        assert result.returncode != 0, f"Actual: {result.output}, Expected: the apply refused"
        assert [(e["files"], e["found_models"], e["found_makes"]) for e in mismatch] == \
            [([self.VIDEO], ["Other Body"], [])], \
            f"Actual: {mismatch}, Expected: one camera_mismatch naming the file and its Model only"
        assert self._of(events, "pipeline_file") == [], \
            "Actual: files were processed, Expected: refused before the first file"
        assert sorted(temp_workspace["target"].rglob("*.mp4")) == [], \
            "Actual: a file reached the target, Expected: nothing organized"

    def test_apply_with_assent_imports_with_the_camera_untouched(self, temp_workspace, test_profile):
        """Actual: the organized file still names the camera that shot it
        Expected: the override imports the file, never relabels it
        """
        self._video(temp_workspace, Make="Test", Model="Other Body")

        result = self._run(temp_workspace, test_profile, "--apply", "--allow-camera-mismatch")

        organized = sorted(temp_workspace["target"].rglob("*.mp4"))
        assert result.returncode == 0, f"Actual: {result.output}, Expected: a clean run"
        assert len(organized) == 1, f"Actual: {organized}, Expected: one organized file"
        assert self._camera(organized[0]) == ("Test", "Other Body"), \
            f"Actual: {self._camera(organized[0])}, Expected: ('Test', 'Other Body')"

    def test_dry_run_reports_the_mismatch_and_previews_anyway(self, temp_workspace, test_profile):
        """Actual: camera_mismatch is reported and the file is still previewed
        Expected: the preview tells the user what the apply will ask about
        """
        self._video(temp_workspace, Make="Test", Model="Other Body")

        result = self._run(temp_workspace, test_profile)

        events = self._events(result.stdout)
        assert result.returncode == 0, f"Actual: {result.output}, Expected: a full preview"
        assert len(self._of(events, "camera_mismatch")) == 1
        assert len(self._of(events, "pipeline_file")) == 1, \
            "Actual: the file was not previewed, Expected: previewed anyway"

    def test_matching_camera_differing_only_in_case_is_not_a_mismatch(
            self, temp_workspace, test_profile):
        """Cameras write SONY where profiles say Sony: the same camera."""
        self._video(temp_workspace, Make="TEST", Model="CAMERA")

        result = self._run(temp_workspace, test_profile, "--apply")

        events = self._events(result.stdout)
        assert result.returncode == 0, f"Actual: {result.output}, Expected: a clean run"
        assert self._of(events, "camera_mismatch") == []

    def test_profile_without_a_camera_checks_nothing(self, temp_workspace, test_profile):
        """Media that records no camera gets a hand-named profile with none;
        there is nothing to hold its files to, so nothing is refused."""
        self._set_profile_exif({})
        self._video(temp_workspace, Make="SONY", Model="ILCE-7M5")

        result = self._run(temp_workspace, test_profile, "--apply")

        events = self._events(result.stdout)
        assert result.returncode == 0, f"Actual: {result.output}, Expected: a clean run"
        assert self._of(events, "camera_mismatch") == []
