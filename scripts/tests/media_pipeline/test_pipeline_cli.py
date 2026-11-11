"""
media-pipeline's command line and JSONL contract, end to end.

These run media-pipeline.sh as the app does — a fresh process with stdout piped —
and hold its argument handling, its dry-run and apply modes, the summary, and
the JSONL events the app reads (scripts/lib/media_pipeline/pipeline-schema.yaml).
"""

import json
import os
from pathlib import Path

import yaml

from helpers.media import create_test_video as _create_video_raw
from helpers.pipeline import create_test_video, get_exif_field, run_in_process, run_pipeline
from helpers.pipeline_schema import validate_event
from lib.exiftool import MetadataWriteRefused, exiftool


class TestDryRunMode:
    """Tests for dry run (no --apply) behavior."""

    def test_dry_run_does_not_move_files(self, temp_workspace, test_profile):
        """Without --apply, files are not moved."""
        source = temp_workspace["source"]
        target = temp_workspace["target"]
        video = source / "2025-10-05" / "test.mp4"
        create_test_video(video)

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test"],
        )

        assert video.exists(), "Source file should still exist"
        assert not any(target.rglob("*.mp4")), "No files should be in target"
        assert "DRY RUN" in result.output

    def test_dry_run_does_not_modify_metadata(self, temp_workspace, test_profile):
        """Without --apply, exif metadata is not modified."""
        source = temp_workspace["source"]
        video = source / "2025-10-05" / "test.mp4"
        create_test_video(video)

        original_dto = get_exif_field(video, "DateTimeOriginal")

        run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test"],
        )

        new_dto = get_exif_field(video, "DateTimeOriginal")
        assert original_dto == new_dto, "DateTimeOriginal should not change in dry run"


class TestApplyMode:
    """Tests for apply mode behavior."""

    def test_apply_moves_files_to_organized_structure(self, temp_workspace, test_profile):
        """With --apply, files are moved to target with date structure."""
        source = temp_workspace["source"]
        target = temp_workspace["target"]
        video = source / "2025-10-05" / "test.mp4"
        create_test_video(video, media_create_date="2025:10:05 01:00:00")

        run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "TestGroup", "--apply"],
        )

        assert video.exists(), "Source file should be preserved"
        expected = target / "2025" / "TestGroup" / "2025-10-05" / "test.mp4"
        assert expected.exists(), f"File should be at {expected}"

    def test_apply_writes_datetime_original(self, temp_workspace, test_profile):
        """With --apply, DateTimeOriginal is written if missing."""
        source = temp_workspace["source"]
        target = temp_workspace["target"]
        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:10:05 01:00:00")

        # Verify DateTimeOriginal is not set
        assert get_exif_field(video, "DateTimeOriginal") == ""

        run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test", "--apply"],
        )

        # Find the moved file
        moved = list(target.rglob("*.mp4"))[0]
        dto = get_exif_field(moved, "DateTimeOriginal")
        assert dto == "2025:10:05 10:00:00+09:00", f"DateTimeOriginal should be set, got: {dto}"

    def test_apply_sets_keys_creation_date(self, temp_workspace, test_profile):
        """With --apply, Keys:CreationDate is set with timezone."""
        source = temp_workspace["source"]
        target = temp_workspace["target"]
        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:10:05 01:00:00")

        run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test", "--apply"],
        )

        moved = list(target.rglob("*.mp4"))[0]
        creation_date = get_exif_field(moved, "CreationDate")
        assert "+09:00" in creation_date or "+0900" in creation_date


class TestSummaryOutput:
    """Tests for summary output at end of pipeline."""

    def test_summary_shows_correct_counts(self, temp_workspace, test_profile):
        """Summary shows accurate processed/succeeded/changed counts."""
        source = temp_workspace["source"]
        create_test_video(source / "test1.mp4")
        create_test_video(source / "test2.mp4")
        create_test_video(source / "test3.mp4")

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test", "--apply"],
        )

        assert "Total files processed: 3" in result.stderr
        assert "Successfully completed: 3" in result.stderr

    def test_summary_shows_failed_files(self, temp_workspace, test_profile):
        """Summary lists files that failed processing."""
        source = temp_workspace["source"]
        video = source / "test.mp4"
        create_test_video(video)
        # Make file unreadable to cause failure
        video.chmod(0o000)

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test", "--apply"],
        )

        # Restore permissions for cleanup
        video.chmod(0o644)

        assert "Failed: 1" in result.stderr or result.returncode != 0


class TestCLIArguments:
    """Tests for CLI argument handling."""

    def test_group_is_optional(self, temp_workspace, test_profile):
        """--group is optional; pipeline runs without it."""
        source = temp_workspace["source"]
        create_test_video(source / "test.mp4")

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900"],
        )

        assert result.returncode == 0
        assert "Found 1 .mp4 file(s)" in result.stderr

    def test_source_defaults_to_profile_source_dir(self, temp_workspace, test_profile):
        """Without --source, uses profile's source_dir."""
        source = temp_workspace["source"]
        create_test_video(source / "test.mp4")

        result = run_pipeline(
            ["--profile", test_profile, "--timezone", "+0900", "--group", "Test"],
        )

        assert str(source) in result.stderr
        assert "Found 1 .mp4 file(s)" in result.stderr

    def test_target_from_profile_ready_dir(self, temp_workspace, test_profile):
        """--target defaults to profile's ready_dir."""
        source = temp_workspace["source"]
        target = temp_workspace["target"]
        create_test_video(source / "test.mp4")

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test"],
        )

        assert str(target) in result.stderr


class TestSourceAndTargetMustNotOverlap:
    """A run whose source and target share files is refused before anything is touched.

    The source is a read-only input, so a file renamed on its way out lands in the
    target beside its original instead of replacing it; when the two are the same
    library, every corrected file becomes a duplicate. archive-source would also
    archive or delete the whole library as if it were a card. Overlap is decided on
    real paths, so a symlink to the source is the source.
    """

    @staticmethod
    def _tree(root: Path) -> set[str]:
        return {str(p.relative_to(root)) for p in root.rglob("*")}

    def _assert_refused_untouched(self, workspace: dict, source: Path, target: Path,
                                  test_profile: str) -> None:
        root = workspace["root"]
        create_test_video(source / "VID_20250101_000000.mp4")
        before = self._tree(root)

        result = run_in_process([
            "--profile", test_profile, "--source", str(source), "--target", str(target),
            "--timezone", "+0900", "--tasks", "archive-source",
            "--update-filename-dates", "--apply",
            "--working-dir", str(target / "working"),
        ])

        after = self._tree(root)
        assert result.returncode != 0, "an overlapping source and target should be refused"
        assert after == before, (
            f"nothing should be created, moved or removed\n"
            f"  added:   {sorted(after - before)}\n"
            f"  removed: {sorted(before - after)}")

    def test_same_directory_is_refused(self, temp_workspace, test_profile):
        source = temp_workspace["source"]
        self._assert_refused_untouched(temp_workspace, source, source, test_profile)

    def test_target_inside_source_is_refused(self, temp_workspace, test_profile):
        source = temp_workspace["source"]
        self._assert_refused_untouched(temp_workspace, source, source / "Ready", test_profile)

    def test_source_inside_target_is_refused(self, temp_workspace, test_profile):
        target = temp_workspace["target"]
        source = target / "2025" / "2025-01-01"
        source.mkdir(parents=True)
        self._assert_refused_untouched(temp_workspace, source, target, test_profile)

    def test_symlink_to_source_as_target_is_refused(self, temp_workspace, test_profile):
        source = temp_workspace["source"]
        link = temp_workspace["root"] / "library-link"
        link.symlink_to(source)
        self._assert_refused_untouched(temp_workspace, source, link, test_profile)

    def test_sibling_sharing_a_name_prefix_is_not_overlap(self, temp_workspace, test_profile):
        """'source' and 'source-ready' are separate folders; a string-prefix check
        would wrongly refuse them."""
        source = temp_workspace["source"]
        target = temp_workspace["root"] / "source-ready"
        create_test_video(source / "test.mp4")

        run_in_process([
            "--profile", test_profile, "--source", str(source), "--target", str(target),
            "--timezone", "+0900", "--apply",
        ])

        assert (source / "test.mp4").exists(), "the source file should be kept"
        assert [p.name for p in target.rglob("*.mp4")] == ["test.mp4"], \
            "the file should be copied into the target"


class TestCLIOverrides:
    """Tests for --tags, --make, --model CLI overrides that take precedence over profile values."""

    def test_make_model_override_profile(self, temp_workspace, test_profile):
        """--make and --model override profile's exif.make and exif.model."""
        source = temp_workspace["source"]
        target = temp_workspace["target"]
        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:10:05 01:00:00")

        run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
            "--make", "OverrideMake",
            "--model", "OverrideModel",
            "--apply",
        ])

        moved = list(target.rglob("*.mp4"))[0]
        make = get_exif_field(moved, "Make")
        model = get_exif_field(moved, "Model")
        assert make == "OverrideMake", f"Expected Make=OverrideMake, got {make}"
        assert model == "OverrideModel", f"Expected Model=OverrideModel, got {model}"

    def test_target_overrides_profile_ready_dir(self, temp_workspace, test_profile):
        """--target overrides profile's ready_dir, files land in override directory."""
        source = temp_workspace["source"]
        override_target = temp_workspace["root"] / "override_target"
        override_target.mkdir()
        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:10:05 01:00:00")

        run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--target", str(override_target),
            "--timezone", "+0900",
            "--group", "Test",
            "--apply",
        ])

        profile_target = temp_workspace["target"]
        assert not any(profile_target.rglob("*.mp4")), "No files should be in profile's ready_dir"
        assert any(override_target.rglob("*.mp4")), "Files should be in override target directory"


class TestPipelineMachineOutput:
    """Test JSONL machine-readable output from media-pipeline."""

    def _parse_events(self, stdout: str) -> list[dict]:
        """Parse JSONL events from pipeline stdout, grouping by pipeline_file.

        Every event is checked against pipeline-schema.yaml on the way through, so
        each scenario in this class doubles as a contract test: a field or token the
        schema does not declare fails here rather than reaching the app undecodable.
        """
        files: list[dict] = []
        current: dict = {}
        for line in stdout.strip().split("\n"):
            if not line.strip():
                continue
            event = json.loads(line)
            validate_event(event)
            etype = event["event"]
            if etype == "pipeline_file":
                if current:
                    files.append(current)
                current = {"pipeline_file": event["file"]}
            elif etype == "pipeline_result":
                current["pipeline_result"] = event["result"]
            elif etype == "tag_result":
                current["tag_action"] = event["action"]
                current["tags_added"] = event.get("tags_added")
                current["exif_make"] = event.get("exif_make")
                current["exif_model"] = event.get("exif_model")
            elif etype == "timestamp_result":
                current["timestamp_action"] = event["action"]
                current["original_time"] = event.get("original_time")
                current["corrected_time"] = event.get("corrected_time")
                current["timestamp_source"] = event.get("source")
                current["timezone"] = event.get("timezone")
                current["correction_mode"] = event.get("correction_mode")
                current["requires_force_timezone"] = event.get("requires_force_timezone")
                current["camera_zone_offset"] = event.get("camera_zone_offset")
                current["stale_fields"] = event.get("stale_fields")
                current["time_offset_seconds"] = event.get("time_offset_seconds")
                current["time_offset_display"] = event.get("time_offset_display")
                if event.get("error"):
                    current["timestamp_error"] = event["error"]
            elif etype == "rename_result":
                current["renamed_to"] = event["renamed_to"]
            elif etype == "organize_result":
                current["organize_action"] = event["action"]
                current["dest"] = event["dest"]
                current["organize_reason"] = event.get("reason")
            elif etype == "gyroflow_result":
                current["gyroflow_action"] = event["action"]
                current["gyroflow_path"] = event.get("gyroflow_path")
                if event.get("error"):
                    current["error"] = event["error"]
            elif etype == "stage_complete":
                current.setdefault("stages", []).append(event["stage"])
        if current:
            files.append(current)
        return files

    def test_pipeline_emits_events_per_file(self, temp_workspace, test_profile):
        """Pipeline emits pipeline_file and pipeline_result JSONL events per file.

        Actual: two file groups from two input videos, each with a pipeline_result
        Expected: {test1.mp4, test2.mp4} each with result in {changed, unchanged, would_change}
        """
        source = temp_workspace["source"]
        create_test_video(source / "test1.mp4", media_create_date="2025:10:05 01:00:00")
        create_test_video(source / "test2.mp4", media_create_date="2025:10:05 01:00:00")

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
        ])

        files = self._parse_events(result.stdout)
        actual_names = {f["pipeline_file"] for f in files}
        expected_names = {"test1.mp4", "test2.mp4"}
        assert actual_names == expected_names, \
            f"Actual: file groups {actual_names}, Expected: {expected_names}"
        valid_results = {"changed", "unchanged", "would_change"}
        for f in files:
            actual_result = f.get("pipeline_result")
            assert actual_result in valid_results, \
                f"Actual: pipeline_result={actual_result} for {f['pipeline_file']}, " \
                f"Expected: one of {valid_results}"

    def test_pipeline_emits_stage_events(self, temp_workspace, test_profile):
        """Pipeline emits structured JSONL events for each stage result.

        Actual: raw JSONL events include timestamp_result and organize_result with typed fields
        Expected: timestamp_result has action + time fields, organize_result has dest
        """
        source = temp_workspace["source"]
        create_test_video(source / "test.mp4", media_create_date="2025:10:05 01:00:00")

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
        ])

        raw_events = [json.loads(line) for line in result.stdout.strip().split("\n") if line.strip()]
        event_types = [e["event"] for e in raw_events]
        assert "timestamp_result" in event_types, \
            f"Actual: event types {event_types}, Expected: timestamp_result present"
        assert "organize_result" in event_types, \
            f"Actual: event types {event_types}, Expected: organize_result present"

        ts_event = next(e for e in raw_events if e["event"] == "timestamp_result")
        assert ts_event.get("original_time"), \
            f"Actual: timestamp_result.original_time={ts_event.get('original_time')}, Expected: non-empty timestamp"
        assert ts_event.get("corrected_time"), \
            f"Actual: timestamp_result.corrected_time={ts_event.get('corrected_time')}, Expected: non-empty timestamp"
        assert ts_event.get("action"), \
            f"Actual: timestamp_result.action={ts_event.get('action')}, Expected: non-empty action"

        org_event = next(e for e in raw_events if e["event"] == "organize_result")
        assert org_event.get("dest"), \
            f"Actual: organize_result.dest={org_event.get('dest')}, Expected: non-empty path"
        assert org_event.get("action"), \
            f"Actual: organize_result.action={org_event.get('action')}, Expected: non-empty action"

    def test_pipeline_stdout_only_has_jsonl(self, temp_workspace, test_profile):
        """Pipeline stdout contains only JSONL event lines.

        Actual: every non-empty stdout line is valid JSON with an event key
        Expected: clean machine-readable output on stdout, human text on stderr
        """
        source = temp_workspace["source"]
        create_test_video(source / "test.mp4", media_create_date="2025:10:05 01:00:00")

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
        ])

        for line in result.stdout.strip().split("\n"):
            if line.strip():
                event = json.loads(line)
                assert "event" in event, f"Actual: stdout line missing 'event' key: {line}"

    def test_gyroflow_runs_in_dry_run(self, temp_workspace, test_profile):
        """Gyroflow step runs in dry run — base script is --apply-aware.

        Actual: no error in stdout when gyroflow is enabled but --apply is not passed
        Expected: gyroflow step runs without error in dry run
        """
        profiles_path = Path(os.environ["JETLAG_PROFILES_FILE"])
        with open(profiles_path) as f:
            profiles = yaml.safe_load(f)
        profiles["profiles"]["_test"]["gyroflow_enabled"] = True
        with open(profiles_path, "w") as f:
            yaml.dump(profiles, f, default_flow_style=False, sort_keys=False)

        source = temp_workspace["source"]
        create_test_video(source / "test.mp4", media_create_date="2025:10:05 01:00:00")

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
            "--tasks", "tag", "gyroflow",
        ])

        files = self._parse_events(result.stdout)
        assert len(files) == 1
        assert "error" not in files[0], f"Gyroflow should be skipped in dry run, got error={files[0].get('error')}"
        assert files[0]["pipeline_result"] in ("changed", "unchanged", "would_change")

    def test_dry_run_emits_would_change(self, temp_workspace, test_profile):
        """Dry run emits pipeline_result=would_change, not changed.

        Actual: pipeline_result=would_change in stdout for files with pending changes
        Expected: dry run distinguishes from apply mode's 'changed' token
        """
        source = temp_workspace["source"]
        create_test_video(source / "test.mp4", media_create_date="2025:10:05 01:00:00")

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
        ])

        files = self._parse_events(result.stdout)
        assert len(files) == 1
        assert files[0]["pipeline_result"] == "would_change", \
            f"Dry run should emit would_change, got: {files[0]['pipeline_result']}"

    def test_apply_emits_changed(self, temp_workspace, test_profile):
        """Apply mode emits pipeline_result=changed, not would_change.

        Actual: pipeline_result=changed in stdout for files with applied changes
        Expected: apply mode uses 'changed' token
        """
        source = temp_workspace["source"]
        create_test_video(source / "test.mp4", media_create_date="2025:10:05 01:00:00")

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
            "--apply",
        ])

        files = self._parse_events(result.stdout)
        assert len(files) == 1
        assert files[0]["pipeline_result"] == "changed", \
            f"Apply mode should emit changed, got: {files[0]['pipeline_result']}"

    def test_every_per_file_event_has_file_field(self, temp_workspace, test_profile):
        """Each per-file event includes a file field for scoping.

        Actual: all per-file result events include a file field
        Expected: JSONL events are self-contained with file context

        Batch-level events — a stage boundary, or the run's own summary — describe
        the whole run and carry no file, so they are named here rather than left
        to slip through as an event that forgot its scope.
        """
        batch_level = {"stage_complete", "pipeline_summary"}
        source = temp_workspace["source"]
        create_test_video(source / "test.mp4", media_create_date="2025:10:05 01:00:00")

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
        ])

        for line in result.stdout.strip().split("\n"):
            if line.strip():
                event = json.loads(line)
                if event["event"] not in batch_level:
                    assert "file" in event, f"Event {event['event']} should include file field"

    def test_tz_mismatch_informational_in_dry_run(self, temp_workspace, test_profile):
        """A dry run previews a timezone-mismatched file instead of aborting.

        The user asks "what would happen?" — the answer is the full preview,
        with the conflict reported as data: a zone_relabel batch_check the run
        did not stop on, plus a per-file requires_force_timezone flag the app can flag in
        its diff table. Exit status stays 0 so the preview is usable.
        """
        source = temp_workspace["source"]
        video = source / "test.mp4"
        _create_video_raw(
            video,
            MediaCreateDate="2025:10:05 01:00:00",
            CreateDate="2025:10:05 01:00:00",
            DateTimeOriginal="2025:10:05 01:00:00+09:00",
        )

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0200",
            "--tasks",
        ])

        assert result.returncode == 0, \
            f"Dry run should continue past a timezone conflict, got {result.returncode}"

        events = [json.loads(line) for line in result.stdout.strip().split("\n") if line.strip()]
        checks = [e for e in events if e.get("event") == "batch_check"]
        assert [(c["check"], c["groups"], c["chosen"], c["refused"]) for c in checks] == \
            [("zone_relabel", {"+0900": ["test.mp4"]}, ["+0200"], False)], \
            f"Actual: {checks}, Expected: one zone_relabel the dry run went on past"

        files = self._parse_events(result.stdout)
        assert len(files) == 1, f"Dry run should still preview the file, got: {files}"
        f = files[0]
        assert f.get("timestamp_action") == "would_fix", \
            f"Expected a would_fix preview, got: {f.get('timestamp_action')}"
        assert f.get("requires_force_timezone") is True, \
            f"Preview row should be flagged as needing --force-timezone, got: {f}"

    def test_camera_zone_offset_forwarded_to_timestamp_result(self, temp_workspace, test_profile):
        """The camera's own inferred zone offset reaches the timestamp_result event,
        so the app diff table can show camera zone vs embedded label vs declared zone.

        A camera left on Japan time while shooting in New Zealand: the filename
        records local digits with no zone, and QuickTime:CreateDate records the
        instant in UTC. Their delta is a legal zone offset (+09:00) — the camera's
        own setting — independent of the declared --timezone used to resolve the fix.
        """
        source = temp_workspace["source"]
        video = source / "VID_20260104_033532_00_001.mp4"
        _create_video_raw(video, CreateDate="2026:01:03 18:35:32")

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+1300",
            "--tasks",
        ])

        assert result.returncode == 0

        files = self._parse_events(result.stdout)
        assert len(files) == 1
        assert files[0].get("camera_zone_offset") == "+09:00", \
            f"Expected the inferred camera zone in the preview row, got: {files[0]}"

    def test_stale_fields_forwarded_to_timestamp_result(self, temp_workspace, test_profile):
        """The write tags a correction would touch reach the timestamp_result event,
        so a diff-table row can say what it will write even when its original and
        corrected times are the same string.

        The fixture's DateTimeOriginal and two clock atoms are already right for +08:00;
        only the third atom is eight hours out and Keys:CreationDate is missing.
        """
        source = temp_workspace["source"]
        video = source / "test.mp4"
        _create_video_raw(
            video,
            DateTimeOriginal="2025:06:18 07:25:21+08:00",
            **{"QuickTime:CreateDate": "2025:06:17 23:25:21",
               "QuickTime:MediaCreateDate": "2025:06:18 07:25:21",
               "QuickTime:TrackCreateDate": "2025:06:17 23:25:21"},
        )

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0800",
            "--tasks",
        ])

        files = self._parse_events(result.stdout)
        assert len(files) == 1
        assert files[0].get("stale_fields") == ["Keys:CreationDate", "QuickTime:MediaCreateDate"], \
            f"Expected the write tags that differ in the preview row, got: {files[0]}"

    def test_tz_mismatch_blocks_apply_without_force(self, temp_workspace, test_profile):
        """Applying a timezone-mismatched batch without --force-timezone is refused.

        The dry run is informational, but relabelling a file whose camera already
        recorded a zone is destructive — it needs explicit confirmation.
        """
        source = temp_workspace["source"]
        video = source / "test.mp4"
        _create_video_raw(
            video,
            MediaCreateDate="2025:10:05 01:00:00",
            CreateDate="2025:10:05 01:00:00",
            DateTimeOriginal="2025:10:05 01:00:00+09:00",
        )

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0200",
            "--tasks",
            "--apply",
        ])

        assert result.returncode != 0, "Apply should exit non-zero on timezone conflict"

        events = [json.loads(line) for line in result.stdout.strip().split("\n") if line.strip()]
        checks = [e for e in events if e.get("event") == "batch_check"]
        assert [(c["check"], c["refused"]) for c in checks] == [("zone_relabel", True)], \
            f"Actual: {checks}, Expected: one refused zone_relabel"
        assert not [e for e in events if e.get("event") == "timestamp_result"], \
            "Apply should refuse before touching any file"

    def test_tz_mismatch_proceeds_with_force_timezone(self, temp_workspace, test_profile):
        """With --force-timezone, timezone mismatch is confirmed and the run proceeds.

        The file's actual moment in time is preserved; it is re-expressed in the
        user-provided zone.
        """
        source = temp_workspace["source"]
        video = source / "test.mp4"
        _create_video_raw(
            video,
            MediaCreateDate="2025:10:05 01:00:00",
            CreateDate="2025:10:05 01:00:00",
            DateTimeOriginal="2025:10:05 01:00:00+09:00",
        )

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0200",
            "--force-timezone",
            "--tasks",
        ])

        files = self._parse_events(result.stdout)
        assert len(files) == 1
        f = files[0]
        assert f.get("timestamp_action") == "would_fix", \
            f"Expected would_fix with --force-timezone, got: {f.get('timestamp_action')}"

    def test_mixed_timezones_not_bypassed_by_force_timezone(self, temp_workspace, test_profile):
        """--force-timezone does not bypass the mixed timezones check.

        When files have different embedded timezones, --force-timezone should
        not suppress the mixed_timezones finding — only --allow-mixed-timezones
        should: each check has its own assent.
        """
        source = temp_workspace["source"]
        _create_video_raw(
            source / "file_tokyo.mp4",
            MediaCreateDate="2025:10:05 01:00:00",
            CreateDate="2025:10:05 01:00:00",
            DateTimeOriginal="2025:10:05 10:00:00+09:00",
        )
        _create_video_raw(
            source / "file_berlin.mp4",
            MediaCreateDate="2025:10:05 01:00:00",
            CreateDate="2025:10:05 01:00:00",
            DateTimeOriginal="2025:10:05 03:00:00+02:00",
        )

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--force-timezone",
            "--tasks",
        ])

        assert result.returncode != 0, \
            "Pipeline should still block on mixed timezones even with --force-timezone"
        events = [json.loads(line) for line in result.stdout.strip().split("\n") if line.strip()]
        refused = [e["check"] for e in events if e.get("event") == "batch_check" and e["refused"]]
        assert refused == ["mixed_timezones"], \
            f"Actual: {refused}, Expected: only mixed_timezones refused"

    def test_a_camera_whose_zone_changed_mid_batch_stops_as_mixed(self, temp_workspace, test_profile):
        """The Comedy night Insta360 X6 batch, shaped down to two clips: no zoned
        tag on either, a correct UTC clock on both, and the camera naming one clip
        in UTC-7 and the next in Perth time.

        Actual: the run's batch_check events
        Expected: mixed_timezones, -0700 for the first clip and +0800 for the
        second — the zones the clock and filename show, which the guard used to
        miss because it looked only at zoned tags
        """
        source = temp_workspace["source"]
        _create_video_raw(source / "VID_20261006_002802_00_001.mp4",
                          CreateDate="2026:10:06 07:28:02", MediaCreateDate="2026:10:06 07:28:02")
        _create_video_raw(source / "VID_20261006_203505_00_005.mp4",
                          CreateDate="2026:10:06 12:35:05", MediaCreateDate="2026:10:06 12:35:05")

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0800",
            "--tasks",
        ])

        events = [json.loads(line) for line in result.stdout.strip().split("\n") if line.strip()]
        checks = [e for e in events if e.get("event") == "batch_check"]
        assert [(c["check"], c["groups"], c["refused"]) for c in checks] == [(
            "mixed_timezones",
            {"-0700": ["VID_20261006_002802_00_001.mp4"], "+0800": ["VID_20261006_203505_00_005.mp4"]},
            True,
        )], f"Actual: {checks}, Expected: one refused mixed_timezones, -0700 and +0800"
        assert not [e for e in events if e.get("event") == "timestamp_result"], \
            "Actual: a file was processed, Expected: the batch stops before the first file"

    def test_mixed_timezones_bypassed_by_allow_mixed(self, temp_workspace, test_profile):
        """--allow-mixed-timezones bypasses the mixed timezones check.

        Files with different embedded timezones should proceed when
        --allow-mixed-timezones is passed. The per-file force-timezone
        behavior is controlled separately by --force-timezone.
        """
        source = temp_workspace["source"]
        _create_video_raw(
            source / "file_tokyo.mp4",
            MediaCreateDate="2025:10:05 01:00:00",
            CreateDate="2025:10:05 01:00:00",
            DateTimeOriginal="2025:10:05 10:00:00+09:00",
        )
        _create_video_raw(
            source / "file_berlin.mp4",
            MediaCreateDate="2025:10:05 01:00:00",
            CreateDate="2025:10:05 01:00:00",
            DateTimeOriginal="2025:10:05 03:00:00+02:00",
        )

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--allow-mixed-timezones",
            "--force-timezone",
            "--tasks",
        ])

        events = [json.loads(line) for line in result.stdout.strip().split("\n") if line.strip()]
        refused = [e for e in events if e.get("event") == "batch_check" and e["refused"]]
        assert refused == [], \
            f"Actual: {refused}, Expected: nothing refused with --allow-mixed-timezones"

        files = self._parse_events(result.stdout)
        assert len(files) == 2, f"Both files should be processed, got {len(files)}"

    def test_filename_preflight_blocks_unparseable(self, temp_workspace, test_profile):
        """--infer-from-filename with unparseable filenames blocks before processing.

        Files like C0009.MP4 have no timestamp in their name. The pipeline
        should report a filename_unparseable finding and exit before processing,
        rather than failing mid-batch.
        """
        source = temp_workspace["source"]
        create_test_video(source / "C0009.MP4")

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--infer-from-filename",
            "--tasks",
        ])

        assert result.returncode != 0, "Pipeline should exit non-zero for unparseable filenames"
        events = [json.loads(line) for line in result.stdout.strip().split("\n") if line.strip()]
        checks = [e for e in events if e.get("event") == "batch_check"]
        assert [(c["check"], c["files"], c["refused"]) for c in checks] == \
            [("filename_unparseable", ["C0009.MP4"], True)], \
            f"Actual: {checks}, Expected: one refused filename_unparseable naming C0009.MP4"

    @staticmethod
    def _refuse_writes(monkeypatch):
        """exiftool refusing every write for a reason no fallback answers."""
        def refuse(*_args, **_kwargs):
            raise MetadataWriteRefused("Not a valid MP4")
        monkeypatch.setattr(exiftool, "write_tags", refuse)

    def test_error_field_on_timestamp_result_exception(self, temp_workspace, test_profile, monkeypatch):
        """A file the timestamp step cannot correct carries the reason in its
        timestamp_result, so the app shows it in the diff table instead of a
        generic "Error" label.

        Actual: the timestamp_result of a file exiftool refuses to write
        Expected: action=error, error naming exiftool's reason
        """
        source = temp_workspace["source"]
        create_test_video(source / "test.mp4", media_create_date="2025:10:05 01:00:00")
        self._refuse_writes(monkeypatch)

        result = run_in_process([
            "--profile", test_profile, "--source", str(source), "--timezone", "+0900",
            "--tasks", "--apply",
        ])

        events = [json.loads(line) for line in result.stdout.strip().split("\n") if line.strip()]
        errors = [(e.get("action"), e.get("error")) for e in events if e.get("event") == "timestamp_result"]
        assert errors == [("error", "Not a valid MP4")], \
            f"Actual: {errors}, Expected: one error carrying exiftool's reason"

    def test_error_path_emits_original_time(self, temp_workspace, test_profile, monkeypatch):
        """Error path emits original_time when the file has a known timestamp.

        Actual: original_time present alongside action=error in timestamp_result
        Expected: error paths include available timestamp data for display
        """
        source = temp_workspace["source"]
        create_test_video(source / "test.mp4", media_create_date="2025:10:05 01:00:00")
        self._refuse_writes(monkeypatch)

        result = run_in_process([
            "--profile", test_profile, "--source", str(source), "--timezone", "+0900",
            "--tasks", "--apply",
        ])

        files = self._parse_events(result.stdout)
        assert len(files) == 1
        f = files[0]
        assert f.get("timestamp_action") == "error", \
            f"Expected timestamp_action=error, got: {f.get('timestamp_action')}"
        assert f.get("original_time"), \
            f"Error path should include original_time, got: {f.get('original_time')}"

    def test_pipeline_emits_stage_complete(self, temp_workspace, test_profile):
        """Pipeline emits stage_complete events for each step that runs.

        Actual: stdout contains stage_complete events for ingest, fix-timestamp, output
        Expected: one stage_complete per pipeline step
        """
        source = temp_workspace["source"]
        create_test_video(source / "test.mp4", media_create_date="2025:10:05 01:00:00")

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
        ])

        stages = [
            json.loads(line)["stage"]
            for line in result.stdout.strip().split("\n")
            if line.strip() and json.loads(line)["event"] == "stage_complete"
        ]
        assert "ingest" in stages, f"Missing ingest stage, got: {stages}"
        assert "fix-timestamp" in stages, f"Missing fix-timestamp stage, got: {stages}"
        assert "output" in stages, f"Missing output stage, got: {stages}"

    def test_stage_complete_order(self, temp_workspace, test_profile):
        """Stage completions are emitted in pipeline order.

        Actual: ingest before tag before fix-timestamp before output
        Expected: stages appear in pipeline execution order
        """
        source = temp_workspace["source"]
        create_test_video(source / "test.mp4", media_create_date="2025:10:05 01:00:00")

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
        ])

        stages = [
            json.loads(line)["stage"]
            for line in result.stdout.strip().split("\n")
            if line.strip() and json.loads(line)["event"] == "stage_complete"
        ]
        # Tag may or may not be present (depends on platform), but order must be preserved
        ordered = [s for s in stages if s in ("ingest", "tag", "fix-timestamp", "output")]
        expected_order = ["ingest", "tag", "fix-timestamp", "output"]
        filtered_expected = [s for s in expected_order if s in ordered]
        assert ordered == filtered_expected, f"Stages out of order: {ordered}"
