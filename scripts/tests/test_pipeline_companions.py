"""
Companion files (.thm, .lrv, …) travel with their video, and
--update-filename-dates renames a file and its companions to the corrected time.
"""

import json
import shutil


from conftest import create_test_video as _create_video_raw
from pipeline_helpers import create_test_video, run_in_process


class TestCompanionFiles:
    """Tests for --copy-companion-files flag."""

    def test_companions_copied_alongside_main_file(self, temp_workspace, test_profile):
        """With --copy-companion-files, companion files end up in the same target directory as the main file."""
        source = temp_workspace["source"]
        target = temp_workspace["target"]

        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:10:05 01:00:00")
        (source / "test.thm").write_bytes(b"thumbnail-data")
        (source / "test.lrv").write_bytes(b"lowres-video-data")

        run_in_process([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
            "--copy-companion-files",
            "--apply",
        ])

        expected_dir = target / "2025" / "Test" / "2025-10-05"
        assert (expected_dir / "test.mp4").exists(), "Main file should be in target"
        assert (expected_dir / "test.thm").exists(), "THM companion should be in target"
        assert (expected_dir / "test.lrv").exists(), "LRV companion should be in target"

    def test_companions_not_copied_without_flag(self, temp_workspace, test_profile):
        """Without --copy-companion-files, only the main file appears in target."""
        source = temp_workspace["source"]
        target = temp_workspace["target"]

        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:10:05 01:00:00")
        (source / "test.thm").write_bytes(b"thumbnail-data")
        (source / "test.lrv").write_bytes(b"lowres-video-data")

        run_in_process([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
            "--apply",
        ])

        target_files = list(target.rglob("*"))
        target_file_names = [f.name for f in target_files if f.is_file()]
        assert "test.mp4" in target_file_names, "Main file should be in target"
        assert "test.thm" not in target_file_names, "THM should not be copied without flag"
        assert "test.lrv" not in target_file_names, "LRV should not be copied without flag"

    def test_source_companions_preserved(self, temp_workspace, test_profile):
        """Source companion files are untouched after processing with --copy-companion-files."""
        source = temp_workspace["source"]

        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:10:05 01:00:00")
        thm = source / "test.thm"
        lrv = source / "test.lrv"
        thm.write_bytes(b"thumbnail-data")
        lrv.write_bytes(b"lowres-video-data")

        run_in_process([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
            "--copy-companion-files",
            "--apply",
        ])

        assert thm.exists(), "Source THM should be preserved"
        assert thm.read_bytes() == b"thumbnail-data"
        assert lrv.exists(), "Source LRV should be preserved"
        assert lrv.read_bytes() == b"lowres-video-data"


class TestUpdateFilenameDates:
    """Tests for --update-filename-dates inline rename."""

    def test_rename_updates_filename_date(self, temp_workspace, test_profile):
        """With --update-filename-dates + --time-offset, file is renamed to reflect corrected timestamp.

        Actual: output file has corrected date in filename after time offset
        Expected: VID_20250505_130334 → VID_20250505_140334 after +3600s offset
        """
        source = temp_workspace["source"]
        target = temp_workspace["target"]
        video = source / "VID_20250505_130334_00_001.mp4"
        _create_video_raw(
            video,
            MediaCreateDate="2025:05:05 04:03:34",
            CreateDate="2025:05:05 04:03:34",
        )

        run_in_process([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
            "--time-offset", "3600",
            "--update-filename-dates",
            "--apply",
        ])

        moved = list(target.rglob("*.mp4"))
        assert len(moved) == 1
        assert "20250505_140334" in moved[0].name, \
            f"Expected corrected timestamp in filename, got: {moved[0].name}"

    def test_rename_emits_renamed_to(self, temp_workspace, test_profile):
        """--update-filename-dates emits rename_result with the corrected filename.

        Actual: rename_result event contains renamed_to with shifted timestamp
        Expected: VID_20250505_130334 → VID_20250505_140334 after +3600s offset
        """
        source = temp_workspace["source"]
        video = source / "VID_20250505_130334_00_001.mp4"
        _create_video_raw(
            video,
            MediaCreateDate="2025:05:05 04:03:34",
            CreateDate="2025:05:05 04:03:34",
        )

        result = run_in_process([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
            "--time-offset", "3600",
            "--update-filename-dates",
        ])

        events = [json.loads(line) for line in result.stdout.strip().split("\n") if line.strip()]
        rename_events = [e for e in events if e["event"] == "rename_result"]
        assert rename_events, \
            f"Actual: no rename_result events in {[e['event'] for e in events]}, " \
            "Expected: one rename_result with corrected filename"
        actual_new_name = rename_events[0]["renamed_to"]
        assert "20250505_140334" in actual_new_name, \
            f"Actual: renamed_to={actual_new_name}, " \
            "Expected: filename containing 20250505_140334 (shifted by +3600s)"

    def test_dry_run_rename_organizes_the_real_file(self, temp_workspace, test_profile):
        """A dry run's pending rename must not repoint organize at a file that
        does not exist: every read happens at the real path, and only the
        destination carries the would-be name.

        The reproducing case is a destination that already holds the file under
        its renamed name (a previous apply ran): organize's existing-target size
        comparison then stats the source. Pre-fix it statted the would-be
        renamed source path — FileNotFoundError, killing the whole run with
        'ERROR: [Errno 2] …' and a pipeline_error event, no pipeline_summary.
        """
        source = temp_workspace["source"]
        target = temp_workspace["target"]
        video = source / "VID_20250505_130334_00_001.mp4"
        _create_video_raw(
            video,
            MediaCreateDate="2025:05:05 04:03:34",
            CreateDate="2025:05:05 04:03:34",
        )
        # The earlier apply's outcome: the file already organized under the
        # name the pending rename will produce, identical content.
        organized = target / "2025" / "Test" / "2025-05-05" / "VID_20250505_140334_00_001.mp4"
        organized.parent.mkdir(parents=True)
        shutil.copy2(video, organized)

        result = run_in_process([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
            "--time-offset", "3600",
            "--update-filename-dates",
        ])

        assert "No such file or directory" not in result.output, \
            "Organize statted the would-be renamed path instead of the real file"
        events = [json.loads(line) for line in result.stdout.strip().split("\n") if line.strip()]
        assert not [e for e in events if e["event"] == "pipeline_error"], \
            "The run must not die on a pending rename"
        organize_events = [e for e in events if e["event"] == "organize_result"]
        assert organize_events, "Expected an organize_result event"
        assert organize_events[0]["action"] == "skipped", \
            f"Actual: {organize_events[0]['action']}, Expected: skipped (identical at destination)"
        assert "20250505_140334" in organize_events[0]["dest"], \
            f"Actual dest: {organize_events[0]['dest']}, " \
            "Expected: destination carrying the would-be renamed filename"
        assert [e for e in events if e["event"] == "pipeline_summary"], \
            "The run must reach its summary"
        assert video.exists(), "Dry run must leave the source file untouched"

    def test_no_rename_when_no_parseable_date(self, temp_workspace, test_profile):
        """Files without parseable date in filename produce no rename_result event.

        Actual: event types emitted for test.mp4 (no date pattern in name)
        Expected: no rename_result event since filename has no parseable date
        """
        source = temp_workspace["source"]
        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:10:05 01:00:00")

        result = run_in_process([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
            "--time-offset", "3600",
            "--update-filename-dates",
        ])

        event_types = [json.loads(line)["event"] for line in result.stdout.strip().split("\n") if line.strip()]
        assert "rename_result" not in event_types, \
            f"Actual: rename_result found in {event_types}, " \
            "Expected: no rename_result for unparseable filename 'test.mp4'"

    def test_no_rename_when_time_unchanged(self, temp_workspace, test_profile):
        """No rename when corrected time matches the filename timestamp.

        Actual: event types emitted for VID_20250505_130334 with no time offset
        Expected: no rename_result since filename already matches corrected time
        """
        source = temp_workspace["source"]
        video = source / "VID_20250505_130334_00_001.mp4"
        _create_video_raw(
            video,
            MediaCreateDate="2025:05:05 04:03:34",
            CreateDate="2025:05:05 04:03:34",
        )

        result = run_in_process([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
            "--update-filename-dates",
        ])

        event_types = [json.loads(line)["event"] for line in result.stdout.strip().split("\n") if line.strip()]
        assert "rename_result" not in event_types, \
            f"Actual: rename_result found in {event_types}, " \
            "Expected: no rename_result when filename time is already correct"

    def test_rename_with_companion_files(self, temp_workspace, test_profile):
        """Companion files are renamed alongside the main file.

        Actual: companion files in target have corrected date in filename
        Expected: .thm companion renamed to match main file's new name
        """
        source = temp_workspace["source"]
        target = temp_workspace["target"]
        video = source / "VID_20250505_130334_00_001.mp4"
        _create_video_raw(
            video,
            MediaCreateDate="2025:05:05 04:03:34",
            CreateDate="2025:05:05 04:03:34",
        )
        (source / "VID_20250505_130334_00_001.thm").write_bytes(b"thumbnail")

        run_in_process([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
            "--time-offset", "3600",
            "--update-filename-dates",
            "--copy-companion-files",
            "--apply",
        ])

        target_files = {f.name for f in target.rglob("*") if f.is_file()}
        renamed_mp4 = [f for f in target_files if f.endswith(".mp4")]
        renamed_thm = [f for f in target_files if f.endswith(".thm")]
        assert len(renamed_mp4) == 1
        assert "20250505_140334" in renamed_mp4[0], \
            f"Main file should have corrected date, got: {renamed_mp4[0]}"
        assert len(renamed_thm) == 1
        assert "20250505_140334" in renamed_thm[0], \
            f"Companion should have corrected date, got: {renamed_thm[0]}"
