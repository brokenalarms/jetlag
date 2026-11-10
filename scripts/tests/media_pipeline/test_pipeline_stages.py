"""
A file's trip through the pipeline is the list of stages the run's options
enable, run by one loop. These tests pin both halves in-process, without
exiftool: which stages a set of options routes a file through, and what the
loop does around them — one stage_complete per reporting stage, and a single
failure exit that stops the trip, releases the staged copy without deleting it
and reports the file failed.

The end-to-end tests below them run whole pipelines through stages with real
effects: tagging, and a file exiftool refuses to write.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from lib.media_pipeline import RunOptions, WorkingDir, process_file
from lib.media_pipeline import stages
from lib.media_pipeline.stages import Stage, StageOutcome, enabled_stages, fix_writes_fields
from helpers.pipeline import create_test_video, get_exif_field, has_tag_cmd, run_in_process, run_pipeline

DEFAULT_TASKS = frozenset({"tag", "fix-timestamp", "gyroflow"})
CAMERA_PROFILE = {"tags": ["test-camera"], "exif": {"make": "Test", "model": "Camera"}}


def _opts(**overrides) -> RunOptions:
    values = dict(source_dir="/src", target_dir="/dst", working_dir="/work",
                  extensions=[".mp4"], tasks=DEFAULT_TASKS)
    values.update(overrides)
    return RunOptions(**values)


def _names(opts: RunOptions) -> list[str]:
    return [stage.name for stage in enabled_stages(opts)]


class TestStageRouting:

    def test_ingest_and_output_always_run(self):
        """Actual: with no optional task, only ingest and output
        Expected: the fixed frame of every run"""
        assert _names(_opts(tasks=frozenset())) == ["ingest", "output"]

    def test_default_tasks_with_a_camera_profile(self):
        assert _names(_opts(profile=CAMERA_PROFILE)) == ["ingest", "tag", "fix-timestamp", "output"]

    def test_tag_needs_a_profile(self):
        """Without a profile there is nothing to tag with."""
        assert "tag" not in _names(_opts())

    @pytest.mark.parametrize("profile", [
        {"tags": [], "exif": {}},
        {"tags": [" ", ""], "exif": {"make": "", "model": ""}},
    ], ids=["empty", "blank"])
    def test_tag_needs_tags_or_a_camera(self, profile):
        assert "tag" not in _names(_opts(profile=profile))

    @pytest.mark.parametrize("profile", [
        {"tags": ["a"]}, {"exif": {"make": "Test"}}, {"exif": {"model": "Camera"}},
    ], ids=["tags", "make", "model"])
    def test_any_of_tags_make_or_model_enables_tag(self, profile):
        assert "tag" in _names(_opts(profile=profile))

    def test_rename_follows_fix_timestamp_only_with_update_filename_dates(self):
        assert "rename" not in _names(_opts())
        assert _names(_opts(update_filename_dates=True)) == \
            ["ingest", "fix-timestamp", "rename", "output"]
        assert "rename" not in _names(_opts(tasks=frozenset({"tag"}), update_filename_dates=True))

    @pytest.mark.parametrize("profile,config,enabled", [
        ({"gyroflow_enabled": True}, {"binary": "gyroflow"}, True),
        ({"gyroflow_enabled": False}, {"binary": "gyroflow"}, False),
        ({"gyroflow_enabled": True}, None, False),
        (None, {"binary": "gyroflow"}, False),
    ], ids=["enabled", "profile-off", "no-config", "no-profile"])
    def test_gyroflow_needs_the_task_the_profile_and_a_config(self, profile, config, enabled):
        assert ("gyroflow" in _names(_opts(profile=profile, gyroflow_config=config))) is enabled

    def test_gyroflow_runs_last(self):
        opts = _opts(profile={**CAMERA_PROFILE, "gyroflow_enabled": True}, gyroflow_config={"a": 1})
        assert _names(opts)[-2:] == ["output", "gyroflow"]

    @pytest.mark.parametrize("apply,tasks,expected", [
        (True, DEFAULT_TASKS, True),
        (False, DEFAULT_TASKS, False),
        (True, frozenset({"tag"}), False),
    ], ids=["apply", "dry-run", "no-fix-timestamp"])
    def test_tag_writes_ride_in_fix_timestamps_call_only_when_it_writes(self, apply, tasks, expected):
        """Tag's camera fields go out in fix-timestamp's exiftool write, so the file
        is rewritten once; without that write, tag writes them itself."""
        assert fix_writes_fields(_opts(apply=apply, tasks=tasks)) is expected


class _Recorder:
    """Stands in for emit_event, keeping (event, fields) pairs."""

    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def __call__(self, event_type, **fields):
        self.events.append((event_type, fields))


class _FakeStage(Stage):
    def __init__(self, name, outcome=StageOutcome(), reports=True, ran=None):
        self.name = name
        self.outcome = outcome
        self.reports_completion = reports
        self.ran = ran if ran is not None else []

    def run(self, ctx):
        self.ran.append(self.name)
        return self.outcome


class TestStageLoop:

    @pytest.fixture
    def events(self, monkeypatch):
        recorder = _Recorder()
        monkeypatch.setattr(stages, "emit_event", recorder)
        return recorder

    def _run(self, monkeypatch, stage_list, working=None, **opts):
        monkeypatch.setattr(stages, "STAGES", stage_list)
        working = working or WorkingDir("/work")
        return process_file(Path("/src/clip.mp4"), _opts(**opts), working)

    def test_each_reporting_stage_completes_once_in_order(self, monkeypatch, events):
        """Actual: pipeline_file, a stage_complete per reporting stage, then the result
        Expected: a stage that reports no completion (rename) emits none"""
        result = self._run(monkeypatch, [
            _FakeStage("ingest"), _FakeStage("rename", reports=False),
            _FakeStage("output", StageOutcome(changed=True)),
        ], apply=True)

        assert [(e, f.get("stage") or f.get("result")) for e, f in events.events] == [
            ("pipeline_file", None),
            ("stage_complete", "ingest"),
            ("stage_complete", "output"),
            ("pipeline_result", "changed"),
        ]
        assert result.changed and not result.failed

    @pytest.mark.parametrize("apply,expected", [(True, "changed"), (False, "would_change")])
    def test_any_changing_stage_makes_the_file_changed(self, monkeypatch, events, apply, expected):
        self._run(monkeypatch, [_FakeStage("ingest", StageOutcome(changed=True)), _FakeStage("output")],
                  apply=apply)
        assert events.events[-1] == ("pipeline_result", {"file": "clip.mp4", "result": expected})

    def test_no_changing_stage_leaves_the_file_unchanged(self, monkeypatch, events):
        result = self._run(monkeypatch, [_FakeStage("ingest"), _FakeStage("output")])
        assert events.events[-1] == ("pipeline_result", {"file": "clip.mp4", "result": "unchanged"})
        assert not result.changed

    def test_a_failed_stage_ends_the_trip_once(self, monkeypatch, events, tmp_path):
        """Actual: later stages never run, the failed stage reports no completion,
        one failed pipeline_result, and the staged copy is released but still on disk
        Expected: a failed file is kept for inspection, not cleaned up or half-reported
        """
        staged = tmp_path / "clip.mp4"
        staged.write_bytes(b"copy")
        working = WorkingDir(str(tmp_path), created=True)
        working.stage([staged])
        ran: list[str] = []

        result = self._run(monkeypatch, [
            _FakeStage("ingest", StageOutcome(changed=True), ran=ran),
            _FakeStage("fix-timestamp", StageOutcome(error="exiftool refused"), ran=ran),
            _FakeStage("output", ran=ran),
        ], working=working, apply=True)

        assert ran == ["ingest", "fix-timestamp"]
        assert [(e, f.get("stage") or f.get("result")) for e, f in events.events] == [
            ("pipeline_file", None),
            ("stage_complete", "ingest"),
            ("pipeline_result", "failed"),
        ]
        assert (result.failed, result.error, result.changed) == (True, "exiftool refused", False)
        assert working.staged == [] and staged.exists()



@pytest.mark.skipif(
    sys.platform != "darwin" or not has_tag_cmd(),
    reason="requires macOS and the 'tag' command (brew install tag)"
)
class TestTagging:
    """Tests for file tagging from profile."""

    def test_applies_tags_from_profile(self, temp_workspace, test_profile):
        """Tags from profile are applied to files."""
        source = temp_workspace["source"]
        video = source / "test.mp4"
        create_test_video(video)

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test", "--apply"],
        )

        event_types = [json.loads(line)["event"] for line in result.stdout.strip().split("\n") if line.strip()]
        assert "tag_result" in event_types, \
            f"Actual: event types {event_types}, Expected: tag_result present"

    def test_applies_exif_make_model_from_profile(self, temp_workspace, test_profile):
        """EXIF Make/Model from profile are applied."""
        source = temp_workspace["source"]
        target = temp_workspace["target"]
        video = source / "test.mp4"
        create_test_video(video)

        run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test", "--apply"],
        )

        moved = list(target.rglob("*.mp4"))[0]
        make = get_exif_field(moved, "Make")
        model = get_exif_field(moved, "Model")
        assert make == "Test"
        assert model == "Camera"


class TestFileExiftoolCannotWrite:
    """exiftool reads some files it refuses to rewrite, saying why on stderr and
    "0 image files updated" on stdout. A camera's malformed atoms are one source;
    trailing bytes past the last atom are the same refusal on any MP4. Such a file
    must fail with exiftool's reason and stay out of the library: it carries none
    of the metadata the run says it applied.
    """

    @staticmethod
    def _create_unwritable_video(path: Path):
        create_test_video(path)
        with open(path, "ab") as f:
            f.write(b"\0\x0f\x42\x40free" + b"\0" * 16)

    @staticmethod
    def _events(stdout: str) -> list[dict]:
        return [json.loads(line) for line in stdout.splitlines() if line.startswith("{")]

    def test_timestamp_write_refused_fails_the_file_with_exiftools_reason(self, temp_workspace, test_profile):
        source, target = temp_workspace["source"], temp_workspace["target"]
        self._create_unwritable_video(source / "VID_20251005_100000.mp4")

        result = run_in_process([
            "--profile", test_profile, "--source", str(source),
            "--timezone", "+0900", "--infer-from-filename", "--apply",
        ])

        events = self._events(result.stdout)
        timestamp = next(e for e in events if e["event"] == "timestamp_result")
        outcome = next(e for e in events if e["event"] == "pipeline_result")
        organized = [p for p in target.rglob("*.mp4")]
        assert timestamp["action"] == "error", f"Actual: {timestamp}, Expected: action=error"
        assert "garbage at end of file" in timestamp.get("error", ""), \
            f"Actual: error={timestamp.get('error')!r}, Expected: exiftool's own reason"
        assert outcome["result"] == "failed", f"Actual: {outcome}, Expected: failed"
        assert organized == [], f"Actual: {organized} organized, Expected: nothing in the library"
        assert "changes applied" not in result.stderr, \
            "Actual: summary says changes applied, Expected: it names the failure"

    def test_camera_write_refused_fails_the_file_when_tagging_writes_alone(self, temp_workspace, test_profile):
        source, target = temp_workspace["source"], temp_workspace["target"]
        self._create_unwritable_video(source / "VID_20251005_100000.mp4")

        result = run_in_process([
            "--profile", test_profile, "--source", str(source),
            "--timezone", "+0900", "--tasks", "tag", "--apply",
        ])

        events = self._events(result.stdout)
        outcome = next(e for e in events if e["event"] == "pipeline_result")
        organized = [p for p in target.rglob("*.mp4")]
        assert outcome["result"] == "failed", f"Actual: {outcome}, Expected: failed"
        assert organized == [], f"Actual: {organized} organized, Expected: nothing in the library"
        assert "garbage at end of file" in result.stderr, \
            f"Actual: {result.stderr[-800:]}, Expected: exiftool's own reason"
