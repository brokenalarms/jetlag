"""
The archive-source step: what happens to the source folder once every file is
through, and why a failed file stops it.
"""

from datetime import datetime


from helpers.pipeline import create_test_video, run_pipeline


class TestArchiveSourceIntegration:
    """Tests for archive-source task integration in the pipeline."""

    def test_archive_renames_source_dir(self, temp_workspace, test_profile):
        """With archive-source task and --source-action archive, source dir is renamed."""
        source = temp_workspace["source"]

        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:10:05 01:00:00")

        run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
            "--tasks", "tag", "fix-timestamp", "archive-source",
            "--source-action", "archive",
            "--apply",
        ])

        today = datetime.now().strftime("%Y-%m-%d")
        expected_renamed = source.parent / f"{source.name} - copied {today}"
        assert expected_renamed.exists(), f"Source should be renamed to {expected_renamed.name}"
        assert not source.exists(), "Original source dir should no longer exist"

    def test_delete_removes_processed_files(self, temp_workspace, test_profile):
        """With --source-action delete, processed source files are removed."""
        source = temp_workspace["source"]

        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:10:05 01:00:00")
        unrelated = source / "notes.txt"
        unrelated.write_bytes(b"keep me")

        run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
            "--tasks", "tag", "fix-timestamp", "archive-source",
            "--source-action", "delete",
            "--apply",
        ])

        assert not video.exists(), "Processed video should be deleted from source"
        assert unrelated.exists(), "Unrelated file should survive"

    def test_archive_destination_and_name_move_the_source_dir(self, temp_workspace, test_profile):
        """The pipeline passes --archive-destination and --archived-name through
        to archive-source, so the app can move the card's folder somewhere else
        under a name the user chose."""
        source = temp_workspace["source"]
        elsewhere = source.parent / "Archive"
        elsewhere.mkdir()

        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:10:05 01:00:00")

        run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
            "--tasks", "tag", "fix-timestamp", "archive-source",
            "--archive-destination", str(elsewhere),
            "--archived-name", "Japan trip",
            "--apply",
        ])

        moved = elsewhere / "Japan trip"
        assert moved.is_dir(), f"Source should be moved to {moved}"
        assert not source.exists(), "Original source dir should no longer exist"

    def test_archive_source_not_run_by_default(self, temp_workspace, test_profile):
        """Default tasks do not include archive-source, so source is untouched."""
        source = temp_workspace["source"]

        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:10:05 01:00:00")

        run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
            "--apply",
        ])

        assert source.exists(), "Source dir should be untouched with default tasks"
        assert video.exists(), "Source file should still exist"

    def test_archive_skipped_when_a_file_failed(self, temp_workspace, test_profile):
        """A failed file's only copy may still be in the source directory, so
        archive-source must not run — in apply or dry-run mode — when any file
        in the batch failed."""
        source = temp_workspace["source"]

        good = source / "good.mp4"
        create_test_video(good)
        bad = source / "bad.mp4"
        create_test_video(bad)
        bad.chmod(0o000)

        try:
            result = run_pipeline([
                "--profile", test_profile,
                "--source", str(source),
                "--timezone", "+0900",
                "--group", "Test",
                "--tasks", "tag", "fix-timestamp", "archive-source",
                "--source-action", "archive",
                "--apply",
            ])
        finally:
            if bad.exists():
                bad.chmod(0o644)

        assert "Failed: 1" in result.stderr
        assert source.exists(), "Source dir should not be archived away after a failure"
        today = datetime.now().strftime("%Y-%m-%d")
        not_expected = source.parent / f"{source.name} - copied {today}"
        assert not not_expected.exists(), "Source should not have been renamed"
        assert "Skipping archive source" in result.stderr
        skip_line = next(line for line in result.stderr.split("\n") if "Skipping archive source" in line)
        assert "1" in skip_line, f"Skip line should mention the failed count: {skip_line}"
        assert "Archive source..." not in result.stderr

    def test_archive_source_with_companions(self, temp_workspace, test_profile):
        """Archive-source with companions: companions included in source file list for delete."""
        source = temp_workspace["source"]

        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:10:05 01:00:00")
        thm = source / "test.thm"
        thm.write_bytes(b"thumbnail-data")

        run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
            "--tasks", "tag", "fix-timestamp", "archive-source",
            "--source-action", "delete",
            "--copy-companion-files",
            "--apply",
        ])

        assert not video.exists(), "Processed video should be deleted from source"
        assert not thm.exists(), "Companion THM should be deleted from source"
