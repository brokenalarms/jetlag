"""
The output stage: where a file lands in the target (group and folder template),
what the run says it did with it, and what happens when the destination already
holds a file.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

from helpers.pipeline import create_test_video, run_in_process, run_pipeline
from helpers.pipeline_schema import validate_event


class TestPipelineOutcomeLines:
    """The pipeline states the user-facing outcome; organize states its own.

    Each script logs the operation it actually performed and the pipeline
    collates those lines verbatim, so organize — which is handed the staged
    working copy on an apply — truthfully names that copy in its own line.
    Beside it the pipeline adds one line per file naming the user's source
    and the final destination, which is the outcome the user cares about.
    The working dir therefore appears only in organize's own line, never in
    a pipeline-owned one, and on failure only in the preserved-for-inspection
    line.
    """

    PIPELINE_OWNED_MARKERS = ("Copied:", "Would copy:", "Replaced at destination:",
                              "Would replace at destination:", "→ Working:")

    def test_dry_run_never_mentions_working_dir(self, temp_workspace, test_profile):
        """A dry run's stderr never contains the working dir path."""
        source = temp_workspace["source"]
        create_test_video(source / "test1.mp4")
        create_test_video(source / "test2.mp4")
        working_dir = tempfile.mkdtemp(prefix="pipeline_working_")

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900",
             "--group", "Test", "--working-dir", working_dir],
        )

        assert working_dir not in result.output

    def test_dry_run_prints_one_organize_line_per_file(self, temp_workspace, test_profile):
        """A dry run over N files previews N copies, and organize previews N moves."""
        source = temp_workspace["source"]
        sources = [source / "test1.mp4", source / "test2.mp4", source / "test3.mp4"]
        for video in sources:
            create_test_video(video)

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test"],
        )

        lines = result.output.split("\n")
        previews = [line for line in lines if "[DRY RUN] Would copy:" in line]
        assert len(previews) == 3, \
            f"Actual: {len(previews)} pipeline preview lines, Expected: 3\n{result.output}"
        for video in sources:
            assert any(str(video) in line and str(temp_workspace["target"]) in line
                       for line in previews), \
                f"Actual: no preview naming {video} and the target, got:\n" + "\n".join(previews)

        assert len([line for line in lines if "Would move:" in line]) == 3, \
            "Actual: organize did not preview one move per file, Expected: 3"

    def test_apply_prints_one_copied_line_per_file_naming_the_source(
        self, temp_workspace, test_profile
    ):
        """An apply reports each file as copied from the user's source to the destination."""
        source = temp_workspace["source"]
        sources = [source / "test1.mp4", source / "test2.mp4"]
        for video in sources:
            create_test_video(video)

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900",
             "--group", "Test", "--apply"],
        )

        copied = [line for line in result.output.split("\n") if "✅ Copied:" in line]
        assert len(copied) == 2, \
            f"Actual: {len(copied)} '✅ Copied:' lines, Expected: 2\n{result.output}"
        for video in sources:
            assert any(str(video) in line and str(temp_workspace["target"]) in line
                       for line in copied), \
                f"Actual: no copied line naming {video} and the target, got:\n" + "\n".join(copied)

    def test_apply_names_the_working_dir_only_in_organizes_own_line(
        self, temp_workspace, test_profile
    ):
        """Organize truthfully names the staged copy it moved; no pipeline line does."""
        source = temp_workspace["source"]
        create_test_video(source / "test.mp4")
        working_dir = tempfile.mkdtemp(prefix="pipeline_working_")

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900",
             "--group", "Test", "--working-dir", working_dir, "--apply"],
        )

        mentions = [line for line in result.output.split("\n") if working_dir in line]
        assert mentions, \
            f"Actual: nothing named the staged copy, Expected: organize's own move line\n{result.output}"
        for line in mentions:
            assert "✅ Moved:" in line, \
                f"Actual: {line!r} names the working dir, Expected: only organize's move line does"
            assert not any(marker in line for marker in self.PIPELINE_OWNED_MARKERS), \
                f"Actual: a pipeline-owned line names the working dir: {line!r}"

    def test_apply_mentions_working_dir_only_when_preserved_for_inspection(
        self, temp_workspace, test_profile
    ):
        """On failure, the working dir is named only in the preserved-for-inspection line."""
        source = temp_workspace["source"]
        video = source / "test.mp4"
        create_test_video(video)
        video.chmod(0o000)
        working_dir = tempfile.mkdtemp(prefix="pipeline_working_")

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900",
             "--group", "Test", "--working-dir", working_dir, "--apply"],
        )

        video.chmod(0o644)

        mentions = [line for line in result.output.split("\n") if working_dir in line]
        assert len(mentions) == 1
        assert "preserved for inspection" in mentions[0]


class TestGroupTemplate:
    """Tests for --group parameter and path template."""

    def test_group_creates_correct_path_structure(self, temp_workspace, test_profile):
        """--group creates YYYY/GROUP/YYYY-MM-DD structure."""
        source = temp_workspace["source"]
        target = temp_workspace["target"]
        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:08:15 03:00:00")

        result = run_in_process(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "South Korea Trip", "--apply"],
        )

        actual_files = list(target.rglob("*.mp4"))
        expected = target / "2025" / "South Korea Trip" / "2025-08-15" / "test.mp4"
        assert expected.exists(), f"Expected: {expected}\nActual files: {actual_files}\nStdout: {result.stdout[-500:]}\nStderr: {result.stderr}"

    def test_group_with_special_characters(self, temp_workspace, test_profile):
        """Group names with special characters work correctly."""
        source = temp_workspace["source"]
        target = temp_workspace["target"]
        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:08:15 03:00:00")

        run_in_process(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "08-09 - South Korea", "--apply"],
        )

        expected = target / "2025" / "08-09 - South Korea" / "2025-08-15" / "test.mp4"
        assert expected.exists()

    def test_without_group_uses_flat_date_structure(self, temp_workspace, test_profile):
        """Without --group, files are organized into YYYY/YYYY-MM-DD structure."""
        source = temp_workspace["source"]
        target = temp_workspace["target"]
        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:08:15 03:00:00")

        result = run_in_process(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--apply"],
        )

        actual_files = list(target.rglob("*.mp4"))
        expected = target / "2025" / "2025-08-15" / "test.mp4"
        assert expected.exists(), f"Expected: {expected}\nActual files: {actual_files}\nStdout: {result.stdout[-500:]}\nStderr: {result.stderr}"

    def test_folder_template_with_group(self, temp_workspace, test_profile):
        """Profile folder_template with {{GROUP}} token substitutes the group value."""
        profiles_path = Path(os.environ["JETLAG_PROFILES_FILE"])
        with open(profiles_path) as f:
            profiles = yaml.safe_load(f)
        profiles["profiles"]["_test"]["folder_template"] = "{{YYYY}}/{{MM}}/{{GROUP}}/{{YYYY}}-{{MM}}-{{DD}}"
        with open(profiles_path, "w") as f:
            yaml.dump(profiles, f, default_flow_style=False, sort_keys=False)

        source = temp_workspace["source"]
        target = temp_workspace["target"]
        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:08:15 03:00:00")

        result = run_in_process(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Japan", "--apply"],
        )

        actual_files = list(target.rglob("*.mp4"))
        expected = target / "2025" / "08" / "Japan" / "2025-08-15" / "test.mp4"
        assert expected.exists(), f"Expected: {expected}\nActual files: {actual_files}\nStdout: {result.stdout[-500:]}\nStderr: {result.stderr}"

    def test_folder_template_without_group(self, temp_workspace, test_profile):
        """Without --group, a profile folder_template's {{GROUP}} folder is left out."""
        profiles_path = Path(os.environ["JETLAG_PROFILES_FILE"])
        with open(profiles_path) as f:
            profiles = yaml.safe_load(f)
        profiles["profiles"]["_test"]["folder_template"] = "{{YYYY}}/{{MM}}/{{GROUP}}/{{YYYY}}-{{MM}}-{{DD}}"
        with open(profiles_path, "w") as f:
            yaml.dump(profiles, f, default_flow_style=False, sort_keys=False)

        source = temp_workspace["source"]
        target = temp_workspace["target"]
        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:08:15 03:00:00")

        result = run_in_process(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--apply"],
        )

        actual_files = list(target.rglob("*.mp4"))
        expected = target / "2025" / "08" / "2025-08-15" / "test.mp4"
        assert expected.exists(), f"Expected: {expected}\nActual files: {actual_files}\nStdout: {result.stdout[-500:]}\nStderr: {result.stderr}"


class TestGroupFolder:
    """Tests for --group folder placement."""

    def test_group_folder(self, temp_workspace, test_profile):
        """--group inserts a folder between the year and the date."""
        source = temp_workspace["source"]
        target = temp_workspace["target"]
        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:08:15 03:00:00")

        run_in_process([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Japan",
            "--apply",
        ])

        expected = target / "2025" / "Japan" / "2025-08-15" / "test.mp4"
        actual_files = list(target.rglob("*.mp4"))
        assert expected.exists(), f"Expected: {expected}\nActual files: {actual_files}"


class TestAlreadyProcessedFiles:
    """Tests for handling files that are already correctly processed."""

    def test_skips_already_organized_files(self, temp_workspace, test_profile):
        """Files already in correct target location remain unchanged."""
        target = temp_workspace["target"]
        correct_path = target / "2025" / "Test" / "2025-10-05" / "test.mp4"
        create_test_video(correct_path, media_create_date="2025:10:05 01:00:00")
        subprocess.run(
            ["exiftool", "-overwrite_original", "-DateTimeOriginal=2025:10:05 10:00:00+09:00", str(correct_path)],
            capture_output=True,
        )
        original_size = correct_path.stat().st_size

        run_in_process(
            ["--profile", test_profile, "--source", str(correct_path.parent), "--timezone", "+0900", "--group", "Test", "--apply"],
        )

        assert correct_path.exists(), "File should still be at the organized location"
        assert correct_path.stat().st_size == original_size, "File content should be unchanged"
        all_mp4s = list(target.rglob("*.mp4"))
        assert len(all_mp4s) == 1, f"Should be exactly one file in target, found: {all_mp4s}"


class TestOutputAlwaysOn:
    """Output (organize) always runs regardless of --tasks selection."""

    def test_fix_timestamp_task_still_outputs(self, temp_workspace, test_profile):
        """--tasks fix-timestamp still moves file to target."""
        source = temp_workspace["source"]
        target = temp_workspace["target"]
        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:10:05 01:00:00")

        run_in_process(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900",
             "--group", "Test", "--tasks", "fix-timestamp", "--apply"],
        )

        output_files = list(target.rglob("*.mp4"))
        assert len(output_files) == 1, f"File should be in target, found: {output_files}"

    def test_tag_task_still_outputs(self, temp_workspace, test_profile):
        """--tasks tag still moves file to target."""
        source = temp_workspace["source"]
        target = temp_workspace["target"]
        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:10:05 01:00:00")

        run_in_process(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900",
             "--group", "Test", "--tasks", "tag", "--apply"],
        )

        output_files = list(target.rglob("*.mp4"))
        assert len(output_files) == 1, f"File should be in target, found: {output_files}"


class TestOverwriteDestination:
    """A file already sitting at the organize destination blocks the move.

    The pipeline reports that as data — every blocked file skips with
    reason=exists_differs and the batch ends with one organize_conflict event
    carrying the count — and only replaces those files when --overwrite says so.
    The app reads the conflict event to ask the user before re-running with the
    flag, so the count and the file list have to be right.
    """

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

    def _seed_differing_destination(self, workspace, profile) -> Path:
        """Organize one file, then make the copy at the destination differ.

        Leaves a fresh source file behind, so the next run has something to
        organize into a destination that is already occupied. The filename
        carries the date because organize reads DateTimeOriginal, which only an
        applied fix has written — without it a dry run would resolve a different
        folder than the apply it previews.
        """
        create_test_video(workspace["source"] / "VID_20251005_100000_00_001.mp4",
                          media_create_date="2025:10:05 01:00:00")
        self._run(workspace, profile, "--apply")

        organized = next(workspace["target"].rglob("VID_20251005_100000_00_001.mp4"))
        with open(organized, "ab") as f:
            f.write(b"x" * 100)

        create_test_video(workspace["source"] / "VID_20251005_100000_00_001.mp4",
                          media_create_date="2025:10:05 01:00:00")
        return organized

    def test_blocked_files_are_reported_as_one_batch_conflict(self, temp_workspace, test_profile):
        """Without --overwrite the file stays put and the batch reports the conflict.

        Actual: destination bytes unchanged, organize_conflict names the file
        Expected: the app has one event to prompt on, listing every blocked file
        """
        organized = self._seed_differing_destination(temp_workspace, test_profile)
        before = organized.read_bytes()

        result = self._run(temp_workspace, test_profile, "--apply")

        events = self._events(result.stdout)
        organize_event = next(e for e in events if e["event"] == "organize_result")
        assert organize_event["action"] == "skipped", \
            f"Actual: organize_result.action={organize_event['action']!r}, Expected: 'skipped'"
        assert organize_event.get("reason") == "exists_differs", \
            f"Actual: organize_result.reason={organize_event.get('reason')!r}, Expected: 'exists_differs'"

        conflicts = [e for e in events if e["event"] == "organize_conflict"]
        assert len(conflicts) == 1, \
            f"Actual: {len(conflicts)} organize_conflict events, Expected: exactly 1 for the batch"
        assert conflicts[0]["count"] == 1, \
            f"Actual: organize_conflict.count={conflicts[0]['count']}, Expected: 1"
        assert conflicts[0]["files"] == ["VID_20251005_100000_00_001.mp4"], \
            f"Actual: organize_conflict.files={conflicts[0]['files']}, Expected: ['VID_20251005_100000_00_001.mp4']"
        assert organized.read_bytes() == before, \
            "Actual: the file at the destination changed, Expected: untouched without --overwrite"

    def test_overwrite_replaces_the_file_at_the_destination(self, temp_workspace, test_profile):
        """--overwrite is what replaces the occupant, and the token says so.

        Actual: destination no longer carries the padding that made it differ
        Expected: action=overwrote and the newly processed file in its place
        """
        organized = self._seed_differing_destination(temp_workspace, test_profile)
        before = organized.read_bytes()
        assert before.endswith(b"x" * 100)

        result = self._run(temp_workspace, test_profile, "--apply", "--overwrite")

        events = self._events(result.stdout)
        organize_event = next(e for e in events if e["event"] == "organize_result")
        assert organize_event["action"] == "overwrote", \
            f"Actual: organize_result.action={organize_event['action']!r}, Expected: 'overwrote'"
        assert not [e for e in events if e["event"] == "organize_conflict"], \
            "Actual: a conflict was reported, Expected: none — --overwrite resolved them"

        after = organized.read_bytes()
        assert after != before, \
            "Actual: destination bytes unchanged, Expected: replaced by the processed source"
        assert not after.endswith(b"x" * 100), \
            "Actual: the old file's padding is still there, Expected: it was replaced"

    def test_dry_run_with_overwrite_previews_without_touching_the_file(self, temp_workspace, test_profile):
        """The preview names the replacement it would make and makes none.

        Actual: action=would_overwrite, destination bytes identical
        Expected: a preview, not a move
        """
        organized = self._seed_differing_destination(temp_workspace, test_profile)
        before = organized.read_bytes()

        result = self._run(temp_workspace, test_profile, "--overwrite")

        events = self._events(result.stdout)
        organize_event = next(e for e in events if e["event"] == "organize_result")
        assert organize_event["action"] == "would_overwrite", \
            f"Actual: organize_result.action={organize_event['action']!r}, Expected: 'would_overwrite'"
        assert organized.read_bytes() == before, \
            "Actual: a dry run changed the destination, Expected: untouched"

    def test_overwrite_lines_name_the_replacement_from_the_users_source(
        self, temp_workspace, test_profile
    ):
        """The log says the destination file is replaced, not that the source moved.

        Actual: one 'Would replace at destination:' preview then one
        'Replaced at destination:' line, each naming the untouched source and
        the destination it lands at
        Expected: the outcome the user sees matches the overwrote token
        """
        organized = self._seed_differing_destination(temp_workspace, test_profile)
        untouched_source = temp_workspace["source"] / "VID_20251005_100000_00_001.mp4"

        preview = self._run(temp_workspace, test_profile, "--overwrite")
        previews = [line for line in preview.output.split("\n")
                    if "Would replace at destination:" in line]
        assert len(previews) == 1, \
            f"Actual: {len(previews)} preview lines, Expected: 1\n{preview.output}"
        assert str(untouched_source) in previews[0] and str(organized) in previews[0], \
            f"Actual: {previews[0]!r}, Expected: it to name {untouched_source} and {organized}"

        applied = self._run(temp_workspace, test_profile, "--apply", "--overwrite")
        replaced = [line for line in applied.output.split("\n")
                    if "Replaced at destination:" in line and "Would" not in line]
        assert len(replaced) == 1, \
            f"Actual: {len(replaced)} replacement lines, Expected: 1\n{applied.output}"
        assert str(untouched_source) in replaced[0] and str(organized) in replaced[0], \
            f"Actual: {replaced[0]!r}, Expected: it to name {untouched_source} and {organized}"

    def test_clean_run_reports_no_conflict(self, temp_workspace, test_profile):
        """Nothing occupies the destination, so there is nothing to prompt about."""
        create_test_video(temp_workspace["source"] / "VID_20251005_100000_00_001.mp4",
                          media_create_date="2025:10:05 01:00:00")

        result = self._run(temp_workspace, test_profile, "--apply")

        events = self._events(result.stdout)
        assert not [e for e in events if e["event"] == "organize_conflict"], \
            "Actual: organize_conflict emitted for a clean run, Expected: none"

    def test_identical_copy_is_not_a_conflict(self, temp_workspace, test_profile):
        """An identical file at the destination is not something to ask about.

        Actual: skipped with reason=identical and no conflict event
        Expected: the prompt is reserved for files whose contents differ
        """
        create_test_video(temp_workspace["source"] / "VID_20251005_100000_00_001.mp4",
                          media_create_date="2025:10:05 01:00:00")
        self._run(temp_workspace, test_profile, "--apply")

        organized = next(temp_workspace["target"].rglob("VID_20251005_100000_00_001.mp4"))
        shutil.copy2(organized, temp_workspace["source"] / "VID_20251005_100000_00_001.mp4")

        result = self._run(temp_workspace, test_profile)

        events = self._events(result.stdout)
        organize_event = next(e for e in events if e["event"] == "organize_result")
        assert organize_event.get("reason") == "identical", \
            f"Actual: organize_result.reason={organize_event.get('reason')!r}, Expected: 'identical'"
        assert not [e for e in events if e["event"] == "organize_conflict"], \
            "Actual: organize_conflict emitted for an identical copy, Expected: none"


class TestOrganizeReportsTheUserFacingOutcome:
    """Organize's token names what happened to the user's file, not the staging hop.

    The source directory is a read-only input: ingest copies each file into the
    working directory and only the separate archive-source step ever touches the
    original. Organize itself is handed the working copy on an apply (so it
    reports "moved") and the source file in a dry run (so it reports
    "would_move"), but neither describes the user's outcome — a new file appears
    at the destination and the source stays where it is. The pipeline therefore
    translates both to copied/would_copy before emitting, which also makes a dry
    run and the apply it previews agree on the token for the same file.
    """

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

    def _organize_actions(self, stdout: str) -> dict[str, str]:
        actions = {}
        for line in stdout.strip().split("\n"):
            if not line.strip():
                continue
            event = json.loads(line)
            validate_event(event)
            if event["event"] == "organize_result":
                actions[event["file"]] = event["action"]
        return actions

    def _seed(self, workspace) -> list[str]:
        names = ["VID_20251005_100000_00_001.mp4",
                 "VID_20251005_110000_00_002.mp4",
                 "VID_20251005_120000_00_003.mp4"]
        for name in names:
            create_test_video(workspace["source"] / name,
                              media_create_date="2025:10:05 01:00:00")
        return names

    def test_dry_run_and_apply_report_the_same_copy_token_for_every_file(
            self, temp_workspace, test_profile):
        """The preview must name the outcome the apply produces, file for file.

        Actual: every organize_result in both runs says would_copy / copied
        Expected: no file is described as a move, and the two runs agree
        """
        names = self._seed(temp_workspace)

        preview = self._organize_actions(
            self._run(temp_workspace, test_profile).stdout)
        applied = self._organize_actions(
            self._run(temp_workspace, test_profile, "--apply").stdout)

        assert preview == {name: "would_copy" for name in names}, \
            f"Actual: {preview}, Expected: would_copy for every file"
        assert applied == {name: "copied" for name in names}, \
            f"Actual: {applied}, Expected: copied for every file"
        previewed_outcome = {"would_copy": "copied", "would_move": "moved",
                             "would_overwrite": "overwrote", "skipped": "skipped"}
        assert {n: previewed_outcome[a] for n, a in preview.items()} == applied, \
            f"Actual: preview {preview} vs applied {applied}, Expected: the same outcome per file"

    def test_a_pipelined_run_never_reports_a_move(self, temp_workspace, test_profile):
        """'moved' would claim the source file left its folder, which never happens.

        Actual: the source files are still in place after the apply
        Expected: no organize_result token describes a move
        """
        names = self._seed(temp_workspace)

        preview = self._organize_actions(
            self._run(temp_workspace, test_profile).stdout)
        applied = self._organize_actions(
            self._run(temp_workspace, test_profile, "--apply").stdout)

        moves = {name: action
                 for actions in (preview, applied)
                 for name, action in actions.items()
                 if action in ("moved", "would_move")}
        assert not moves, \
            f"Actual: {moves} reported as moves, Expected: none — the pipeline stages a copy"

        left_behind = sorted(p.name for p in temp_workspace["source"].iterdir())
        assert left_behind == sorted(names), \
            f"Actual: source holds {left_behind}, Expected: {sorted(names)} — untouched by organize"
