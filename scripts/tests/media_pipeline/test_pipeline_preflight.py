"""
Every batch-level check is declared in CHECKS (lib/media_pipeline/preflight.py)
and run by one runner, which reports each finding as one batch_check event and
stops the run once. The finders are pure over the files' cached reads, so the
first tests pin them without starting exiftool: a wrong answer either relabels a
whole batch to the wrong zone or refuses one that was fine.

The end-to-end tests below them run each check through the real pipeline: what
triggers it, which runs it refuses, and that its assent flag lets the run go on.
Then the two checks with consequences past the refusal: protected source files
and the profile's camera.
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
from lib.media_pipeline.options import RunOptions
from lib.media_pipeline.preflight import (
    ALL_CHECKS, CHECKS, Finding, find_mixed_timezones, find_source_read_only, find_zone_relabel,
)
from helpers.pipeline import create_test_video, run_in_process, run_pipeline
from helpers.pipeline_schema import enum_tokens, load_cli, validate_event


def _opts(timezone_spec="+0900", source_dir="/cards", **overrides) -> RunOptions:
    return RunOptions(source_dir=source_dir, target_dir="/ready", working_dir="/work",
                      extensions=[".mp4"], timezone_spec=timezone_spec, **overrides)


def _events(stdout: str) -> list[dict]:
    events = [json.loads(line) for line in stdout.strip().split("\n") if line.strip()]
    for event in events:
        validate_event(event)
    return events


def _checks(events: list[dict], token: str | None = None) -> list[dict]:
    return [e for e in events if e["event"] == "batch_check" and token in (None, e["check"])]


def _processed(events: list[dict]) -> bool:
    return any(e["event"] == "pipeline_file" for e in events)


class TestFindMixedTimezones:
    """A file's zone is the hierarchy's (FileReading.zone): a zoned tag's, else
    the camera's zone setting from its UTC clock against its filename. The
    Comedy night Insta360 X6 batch carries no zoned tag, while the camera named
    five clips in UTC-7 and two in Perth time: one batch, two camera zones."""

    def test_two_camera_zones_are_mixed_grouped_in_file_order(self, fake_metadata):
        utc_minus_7 = Path("/cards/VID_20261006_002802_00_001.insv")
        perth = Path("/cards/VID_20261006_203505_00_005.insv")
        also_utc_minus_7 = Path("/cards/VID_20261006_061911_00_007.insv")
        fake_metadata.files[str(utc_minus_7)] = {"MovieHeaderCreateDate": "2026:10:06 07:28:02"}
        fake_metadata.files[str(perth)] = {"MovieHeaderCreateDate": "2026:10:06 12:35:05"}
        fake_metadata.files[str(also_utc_minus_7)] = {"MovieHeaderCreateDate": "2026:10:06 13:19:11"}

        finding = find_mixed_timezones([utc_minus_7, perth, also_utc_minus_7], _opts("+0800"))

        assert finding == Finding(
            [utc_minus_7.name, perth.name, also_utc_minus_7.name],
            {"-0700": [utc_minus_7.name, also_utc_minus_7.name], "+0800": [perth.name]})
        assert list(finding.groups) == ["-0700", "+0800"]

    def test_zoned_and_unzoned_files_together_are_mixed(self, fake_metadata):
        """A file with no zone evidence falls in the none group: the user expects a
        batch where only some files say where they were shot to stop as mixed."""
        zoned, bare = Path("/cards/zoned.mp4"), Path("/cards/bare.mp4")
        fake_metadata.files[str(zoned)] = {"DateTimeOriginal": "2025:10:05 10:00:00+09:00"}
        fake_metadata.files[str(bare)] = {"MediaCreateDate": "2025:10:05 01:00:00"}

        finding = find_mixed_timezones([zoned, bare], _opts())

        assert finding is not None
        assert finding.groups == {"+0900": ["zoned.mp4"], "none": ["bare.mp4"]}

    def test_a_batch_with_no_zone_evidence_is_not_mixed(self, fake_metadata):
        a, b = Path("/cards/a.mp4"), Path("/cards/b.mp4")
        fake_metadata.files[str(a)] = {"MediaCreateDate": "2025:10:05 01:00:00"}
        fake_metadata.files[str(b)] = {"MediaCreateDate": "2025:10:05 02:00:00"}

        assert find_mixed_timezones([a, b], _opts()) is None

    def test_a_camera_zone_and_a_tagged_zone_that_agree_are_not_mixed(self, fake_metadata):
        """Korea: half the batch tagged +09:00 by an earlier run, half naive with
        the camera on +09:00."""
        tagged = Path("/cards/VID_20250815_101112_00_001.insv")
        naive = Path("/cards/VID_20250830_101112_00_002.insv")
        fake_metadata.files[str(tagged)] = {"DateTimeOriginal": "2025:08:15 10:11:12+09:00",
                                            "MovieHeaderCreateDate": "2025:08:15 01:11:12"}
        fake_metadata.files[str(naive)] = {"MovieHeaderCreateDate": "2025:08:30 01:11:12"}

        assert find_mixed_timezones([tagged, naive], _opts()) is None


class TestFindZoneRelabel:

    def test_a_tagged_zone_differing_from_the_timezone_given_is_found(self, fake_metadata):
        clip = Path("/cards/clip.mp4")
        fake_metadata.files[str(clip)] = {"DateTimeOriginal": "2025:10:05 10:00:00+08:00"}

        assert find_zone_relabel([clip], _opts("+0900")) == \
            Finding(["clip.mp4"], {"+0800": ["clip.mp4"]}, ["+0900"])

    def test_a_zone_name_given_is_reported_as_the_offset_it_gives(self, fake_metadata):
        """The finding compares like with like: the zone name is held against
        the tag as the offset it had when the file was shot."""
        clip = Path("/cards/clip.mp4")
        fake_metadata.files[str(clip)] = {"DateTimeOriginal": "2025:10:05 10:00:00+05:30"}

        assert find_zone_relabel([clip], _opts("Asia/Hong_Kong")) == \
            Finding(["clip.mp4"], {"+0530": ["clip.mp4"]}, ["+0800"])

    def test_a_tagged_zone_matching_the_timezone_given_is_not(self, fake_metadata):
        clip = Path("/cards/clip.mp4")
        fake_metadata.files[str(clip)] = {"DateTimeOriginal": "2025:10:05 10:00:00+09:00"}

        assert find_zone_relabel([clip], _opts("+0900")) is None

    def test_a_camera_zone_differing_from_the_timezone_given_is_not(self, fake_metadata):
        """A camera left on the previous country's zone is the case jetlag exists
        to correct: only a zoned tag needs --force-timezone to be relabelled."""
        clip = Path("/cards/VID_20250815_101112_00_001.insv")
        fake_metadata.files[str(clip)] = {"MovieHeaderCreateDate": "2025:08:15 01:11:12"}

        assert find_zone_relabel([clip], _opts("+1300")) is None

    def test_a_zone_name_resolves_per_file_across_a_dst_change(self, fake_metadata):
        """A run spanning a DST changeover compares each file with the offset its
        zone had when that file was shot: Pacific/Auckland is not one offset."""
        summer, winter = Path("/cards/summer.mp4"), Path("/cards/winter.mp4")
        fake_metadata.files[str(summer)] = {"DateTimeOriginal": "2025:01:10 10:00:00+13:00"}
        fake_metadata.files[str(winter)] = {"DateTimeOriginal": "2025:07:10 10:00:00+12:00"}

        assert find_zone_relabel([summer, winter], _opts("Pacific/Auckland")) is None
        assert fake_metadata.writes == []


class TestChecksAreDeclaredOnce:
    """The schema enumerates the check tokens and assent flags the app holds
    itself to; ALL_CHECKS is what the script emits. A check added on one side
    only fails here."""

    def test_every_check_token_is_in_the_schema(self):
        assert [c.token for c in ALL_CHECKS] == enum_tokens("batch_check", "check")

    def test_the_schema_assent_flags_are_the_checks_flags_and_apply(self):
        flags = {c.assent_flag for c in ALL_CHECKS if c.assent_flag} | {"--apply"}
        assert set(load_cli()["assent_flags"]) == flags


def _camera_mismatch(source: Path) -> list[str]:
    _create_video_raw(source / "clip.mp4", MediaCreateDate="2025:10:05 01:00:00",
                      CreateDate="2025:10:05 01:00:00", Make="Test", Model="Other Body")
    return []


def _mixed_timezones(source: Path) -> list[str]:
    _create_video_raw(source / "tokyo.mp4", MediaCreateDate="2025:10:05 01:00:00",
                      CreateDate="2025:10:05 01:00:00",
                      DateTimeOriginal="2025:10:05 10:00:00+09:00")
    create_test_video(source / "bare.mp4")
    return []


def _zone_relabel(source: Path) -> list[str]:
    _create_video_raw(source / "tokyo.mp4", MediaCreateDate="2025:10:05 01:00:00",
                      CreateDate="2025:10:05 01:00:00",
                      DateTimeOriginal="2025:10:05 10:00:00+09:00")
    return ["--timezone", "+0200"]


def _filename_unparseable(source: Path) -> list[str]:
    create_test_video(source / "C0009.mp4")
    return ["--infer-from-filename"]


def _source_read_only(source: Path) -> list[str]:
    create_test_video(source / "clip.mp4")
    locked = source.parent / "locked"
    locked.mkdir()
    locked.chmod(0o555)
    return ["--tasks", "archive-source", "--archive-destination", str(locked)]


# token → (makes a batch that triggers it and returns its extra args,
#          dry run refused, apply refused)
SCENARIOS = {
    "camera_mismatch": (_camera_mismatch, False, True),
    "mixed_timezones": (_mixed_timezones, True, True),
    "zone_relabel": (_zone_relabel, False, True),
    "filename_unparseable": (_filename_unparseable, True, True),
    "source_read_only": (_source_read_only, False, True),
}


class TestEveryCheckRunsTheSameWay:
    """One test over the checks a plain video batch can trigger (protected
    sources needs BSD flags and destination_occupied comes after the batch; both
    have their own tests). For each: one batch_check naming the check and its
    files; a dry run and an apply each refuse or go on as the check declares;
    and an apply given the check's assent flag goes on.
    """

    def _run(self, workspace, profile, extra, *flags):
        args = ["--profile", profile, "--source", str(workspace["source"]),
                "--target", str(workspace["target"]), "--extensions", ".mp4", "--tasks"]
        if "--timezone" not in extra:
            args += ["--timezone", "+0900"]
        return run_in_process(args + extra + list(flags))

    @pytest.mark.parametrize("token", sorted(SCENARIOS))
    def test_each_check_reports_refuses_and_takes_assent(self, token, temp_workspace, test_profile):
        make_batch, dry_refused, apply_refused = SCENARIOS[token]
        check = next(c for c in CHECKS if c.token == token)
        extra = make_batch(temp_workspace["source"])

        for flags, refused in (((), dry_refused), (("--apply",), apply_refused)):
            result = self._run(temp_workspace, test_profile, extra, *flags)
            events = _events(result.stdout)
            reported = _checks(events, token)
            assert len(reported) == 1, f"Actual: {_checks(events)}, Expected: one {token}"
            assert reported[0]["refused"] is refused, \
                f"Actual: {reported[0]}, Expected: refused={refused} for {flags}"
            assert reported[0].get("assent_flag") == check.assent_flag
            assert reported[0]["files"], f"Actual: {reported[0]}, Expected: the files it found"
            assert (result.returncode != 0) is refused, \
                f"Actual: exit {result.returncode}, {result.output}, Expected: refused={refused}"
            assert _processed(events) is not refused, \
                "Actual: a refused run processed files, or a run that went on did not"

        if check.assent_flag:
            result = self._run(temp_workspace, test_profile, extra, "--apply", check.assent_flag)
            events = _events(result.stdout)
            assert [e["refused"] for e in _checks(events, token)] == [False]
            assert result.returncode == 0, f"Actual: {result.output}, Expected: assent lets it go on"
            assert _processed(events)

    def test_every_finding_is_reported_before_the_run_stops(self, temp_workspace, test_profile):
        """A batch from another camera that also spans two zones asks about both at
        once, rather than one per re-run.

        Actual: the apply's batch_check events
        Expected: camera_mismatch and mixed_timezones, both refused, no file processed
        """
        source = temp_workspace["source"]
        _create_video_raw(source / "tokyo.mp4", MediaCreateDate="2025:10:05 01:00:00",
                          CreateDate="2025:10:05 01:00:00",
                          DateTimeOriginal="2025:10:05 10:00:00+09:00",
                          Make="Test", Model="Other Body")
        create_test_video(source / "bare.mp4")

        result = self._run(temp_workspace, test_profile, [], "--apply")

        events = _events(result.stdout)
        assert [(e["check"], e["refused"]) for e in _checks(events)] == \
            [("camera_mismatch", True), ("mixed_timezones", True)]
        assert result.returncode != 0
        assert not _processed(events)


@pytest.mark.skipif(not hasattr(os, "chflags"), reason="BSD file flags only")
class TestProtectedSources:
    """A source file carrying the user-immutable flag — what a camera's "Protect"
    becomes on macOS — cannot be imported as it is: every stage rewrites or moves
    its staged copy, and a lock carried onto that copy fails each of them with
    EPERM. Importing it means its copy in the library comes out unprotected, so
    an apply asks first: the batch reports the protected files as one
    protected_sources finding, and only --unlock-protected lets the apply
    proceed. The source itself keeps its lock either way.
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

    def test_apply_without_assent_refuses_before_touching_anything(
            self, temp_workspace, test_profile, locked_source):
        """Actual: the run exits non-zero having reported the protected file,
        with nothing organized
        Expected: an apply never silently drops a protection the user set
        """
        result = self._run(temp_workspace, test_profile, "--apply")

        events = _events(result.stdout)
        assert result.returncode != 0, \
            f"Actual: {result.output}, Expected: the apply refused"
        assert [(e["files"], e["refused"]) for e in _checks(events, "protected_sources")] == \
            [([self.VIDEO], True)], \
            f"Actual: {events}, Expected: one refused protected_sources naming {self.VIDEO}"
        assert not _processed(events), \
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
        """Actual: protected_sources is reported, not refused, and every file is
        still previewed
        Expected: the preview tells the user what the apply will ask about
        """
        result = self._run(temp_workspace, test_profile)

        events = _events(result.stdout)
        assert result.returncode == 0, f"Actual: {result.output}, Expected: a full preview"
        assert [(e["files"], e["refused"]) for e in _checks(events, "protected_sources")] == \
            [([self.VIDEO], False)], \
            f"Actual: {events}, Expected: one protected_sources naming {self.VIDEO}"
        previewed = [e for e in events if e["event"] == "pipeline_result"]
        assert len(previewed) == 1, f"Actual: {previewed}, Expected: the file previewed"

    def test_unprotected_batch_reports_nothing(self, temp_workspace, test_profile):
        """Actual: no protected_sources finding for a batch with no locked files
        Expected: the app has nothing to ask about on an ordinary import
        """
        create_test_video(temp_workspace["source"] / self.VIDEO)

        result = self._run(temp_workspace, test_profile, "--apply")

        assert result.returncode == 0, f"Actual: {result.output}, Expected: a clean run"
        assert _checks(_events(result.stdout), "protected_sources") == []


class TestSourceCameraIsCheckedAgainstTheProfile:
    """Every source file is held to the profile's camera before anything runs.

    A file the camera says was shot on another body means the profile was picked
    for the wrong camera — the sony-a7iv-photo profile once relabelled 143 A7V
    stills. The batch reports such files as one camera_mismatch finding grouped
    by the camera found; a dry run previews anyway, an apply refuses without
    --allow-camera-mismatch, and the file's own camera fields are never
    overwritten. A profile with no camera — for media that records none — is
    not checked.
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

    def _video(self, workspace, **camera):
        _create_video_raw(workspace["source"] / self.VIDEO,
                          MediaCreateDate="2025:10:05 01:00:00",
                          CreateDate="2025:10:05 01:00:00", **camera)

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
        """Actual: the apply exits non-zero naming the file under the Model it
        carries, with nothing organized
        Expected: the wrong profile never imports a batch unasked
        """
        self._video(temp_workspace, Make="Test", Model="Other Body")

        result = self._run(temp_workspace, test_profile, "--apply")

        events = _events(result.stdout)
        mismatch = _checks(events, "camera_mismatch")
        assert result.returncode != 0, f"Actual: {result.output}, Expected: the apply refused"
        assert [(e["files"], e["groups"], e["refused"]) for e in mismatch] == \
            [([self.VIDEO], {"Other Body": [self.VIDEO]}, True)], \
            f"Actual: {mismatch}, Expected: one camera_mismatch naming the file and its Model only"
        assert not _processed(events), \
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

    def test_matching_camera_differing_only_in_case_is_not_a_mismatch(
            self, temp_workspace, test_profile):
        """Cameras write SONY where profiles say Sony: the same camera."""
        self._video(temp_workspace, Make="TEST", Model="CAMERA")

        result = self._run(temp_workspace, test_profile, "--apply")

        events = _events(result.stdout)
        assert result.returncode == 0, f"Actual: {result.output}, Expected: a clean run"
        assert _checks(events, "camera_mismatch") == []

    def test_profile_without_a_camera_checks_nothing(self, temp_workspace, test_profile):
        """Media that records no camera gets a hand-named profile with none;
        there is nothing to hold its files to, so nothing is refused."""
        self._set_profile_exif({})
        self._video(temp_workspace, Make="SONY", Model="ILCE-7M5")

        result = self._run(temp_workspace, test_profile, "--apply")

        events = _events(result.stdout)
        assert result.returncode == 0, f"Actual: {result.output}, Expected: a clean run"
        assert _checks(events, "camera_mismatch") == []


class TestSourceReadOnly:
    """With archive-source on, the folders the source action writes to are
    checked before the first file. A Sony card with its lock switch on mounted
    read-only: the apply copied all 18 clips, the rename failed, and the run
    still reported success with PRIVATE left on the card."""

    def _statvfs_read_only(self, monkeypatch, read_only_path: str):
        real = os.statvfs

        class ReadOnly:
            f_flag = os.ST_RDONLY

        monkeypatch.setattr(os, "statvfs",
                            lambda p: ReadOnly() if str(p) == read_only_path else real(p))

    def test_a_read_only_mount_is_found_though_its_permissions_allow_writing(
            self, tmp_path, monkeypatch):
        """access() reported the locked card's root writable; the mount flag did not."""
        source = tmp_path / "PRIVATE"
        source.mkdir()
        self._statvfs_read_only(monkeypatch, str(tmp_path))

        finding = find_source_read_only([], _opts(source_dir=str(source)))

        assert finding == Finding([str(tmp_path)])

    def test_archive_checks_the_source_parent_and_the_destination(self, tmp_path):
        source = tmp_path / "card" / "PRIVATE"
        source.mkdir(parents=True)
        destination = tmp_path / "archive"
        destination.mkdir()
        destination.chmod(0o555)

        finding = find_source_read_only([], _opts(
            source_dir=str(source), archive_destination=str(destination)))

        assert finding == Finding([str(destination)])

    def test_delete_checks_the_source_itself(self, tmp_path):
        source = tmp_path / "PRIVATE"
        source.mkdir()
        source.chmod(0o555)

        finding = find_source_read_only([], _opts(
            source_dir=str(source), source_action="delete"))

        assert finding == Finding([str(source)])

    def test_writable_folders_are_not_a_finding(self, tmp_path):
        source = tmp_path / "PRIVATE"
        source.mkdir()

        assert find_source_read_only([], _opts(source_dir=str(source))) is None

    def test_apply_stops_before_any_file_reaches_the_target(self, temp_workspace, test_profile):
        """Actual: nothing organized and the source still in place
        Expected: a run that cannot archive does not copy first and fail after
        """
        extra = _source_read_only(temp_workspace["source"])

        result = run_in_process([
            "--profile", test_profile, "--source", str(temp_workspace["source"]),
            "--target", str(temp_workspace["target"]), "--extensions", ".mp4",
            "--timezone", "+0900", *extra, "--apply"])

        assert result.returncode != 0, f"Actual: {result.output}, Expected: the apply refused"
        assert sorted(temp_workspace["target"].rglob("*.mp4")) == []
        assert temp_workspace["source"].exists()


class TestSourceActionFailureIsReported:
    """An archive that fails after the files are through says so as data, so the
    app's completion popup can show it rather than leaving it in the log."""

    def test_a_failed_archive_is_in_the_summary_and_the_exit_code(
            self, temp_workspace, test_profile):
        source = temp_workspace["source"]
        create_test_video(source / "clip.mp4")
        taken = source.parent / "archived"
        taken.mkdir()
        (taken / "already-here").write_text("")

        result = run_in_process([
            "--profile", test_profile, "--source", str(source),
            "--target", str(temp_workspace["target"]), "--extensions", ".mp4",
            "--timezone", "+0900", "--tasks", "archive-source",
            "--archive-destination", str(source.parent), "--archived-name", "archived",
            "--apply"])

        summary = next(e for e in _events(result.stdout) if e["event"] == "pipeline_summary")
        assert summary["source_action_failed"] is True, f"Actual: {summary}"
        assert summary["failed"] == 0
        assert result.returncode != 0, f"Actual: {result.output}, Expected: a non-zero exit"
        assert source.exists()

    def test_a_run_without_archive_source_reports_no_failure(self, temp_workspace, test_profile):
        create_test_video(temp_workspace["source"] / "clip.mp4")

        result = run_in_process([
            "--profile", test_profile, "--source", str(temp_workspace["source"]),
            "--target", str(temp_workspace["target"]), "--extensions", ".mp4",
            "--timezone", "+0900", "--apply"])

        summary = next(e for e in _events(result.stdout) if e["event"] == "pipeline_summary")
        assert summary["source_action_failed"] is False
        assert result.returncode == 0
