"""
Which files a run finds and stages: the declared file types, discovery in the
source, ingest into the working directory, and stale exiftool_tmp directories
that would make exiftool fail.
"""

import os
import sys
from pathlib import Path

import pytest
import yaml

from pipeline_helpers import create_test_video, get_exif_field, run_in_process, run_pipeline


class TestFileTypesMustBeDeclared:
    """A run processes only file types someone chose: from the profile or --extensions."""

    NO_TYPES_ERROR = "file_extensions"

    def _drop_file_extensions(self, profile_name):
        profiles_path = Path(os.environ["JETLAG_PROFILES_FILE"])
        profiles = yaml.safe_load(profiles_path.read_text())
        del profiles["profiles"][profile_name]["file_extensions"]
        profiles_path.write_text(yaml.dump(profiles, sort_keys=False))

    def test_profile_without_file_extensions_is_refused_and_creates_nothing(self, temp_workspace, test_profile):
        """A profile that declares no file types exits 1 naming file_extensions and leaves no target behind."""
        self._drop_file_extensions(test_profile)
        source = temp_workspace["source"]
        create_test_video(source / "clip.mp4")
        target = temp_workspace["root"] / "fresh-target"

        result = run_in_process(["--profile", test_profile, "--source", str(source),
                               "--target", str(target), "--apply"])

        assert result.returncode == 1, f"Actual: {result.returncode}, Expected: 1"
        assert self.NO_TYPES_ERROR in result.stderr, f"Actual: {result.stderr}, Expected: it names file_extensions"
        assert not target.exists(), f"Actual: {target} created, Expected: nothing created"

    def test_run_without_profile_or_extensions_is_refused_and_creates_nothing(self, temp_workspace):
        """A profile-less run that states no file types fails the same way."""
        source = temp_workspace["source"]
        create_test_video(source / "clip.mp4")
        target = temp_workspace["root"] / "fresh-target"

        result = run_in_process(["--source", str(source), "--target", str(target), "--apply"])

        assert result.returncode == 1, f"Actual: {result.returncode}, Expected: 1"
        assert self.NO_TYPES_ERROR in result.stderr, f"Actual: {result.stderr}, Expected: it names file_extensions"
        assert not target.exists(), f"Actual: {target} created, Expected: nothing created"

    def test_run_without_profile_processes_the_extensions_it_is_given(self, temp_workspace):
        """A profile-less run with --extensions .mp4 finds and processes the .mp4 file only."""
        source = temp_workspace["source"]
        create_test_video(source / "clip.mp4")
        (source / "other.mov").write_bytes(b"fake")

        result = run_in_process(["--source", str(source), "--target", str(temp_workspace["target"]),
                               "--extensions", ".mp4", "--timezone", "+0900", "--group", "Test"])

        assert "Found 1 .mp4 file(s)" in result.stderr, f"Actual: {result.stderr}, Expected: one .mp4 found"


class TestFileDiscovery:
    """Tests for file discovery based on profile extensions."""

    def test_finds_files_by_extension(self, temp_workspace, test_profile):
        """Pipeline finds .mp4 files specified in profile."""
        source = temp_workspace["source"]
        create_test_video(source / "2025-10-05" / "test1.mp4")
        create_test_video(source / "2025-10-05" / "test2.mp4")

        result = run_in_process(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test"],
        )

        assert "Found 2 .mp4 file(s)" in result.stderr

    def test_ignores_other_extensions(self, temp_workspace, test_profile):
        """Pipeline ignores files not matching profile extensions."""
        source = temp_workspace["source"]
        create_test_video(source / "2025-10-05" / "test.mp4")
        (source / "2025-10-05" / "test.mov").write_bytes(b"fake")
        (source / "2025-10-05" / "test.txt").write_bytes(b"fake")

        result = run_in_process(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test"],
        )

        assert "Found 1 .mp4 file(s)" in result.stderr

    def test_finds_files_in_subdirectories(self, temp_workspace, test_profile):
        """Pipeline recursively finds files in subdirectories."""
        source = temp_workspace["source"]
        create_test_video(source / "2025-10-05" / "test1.mp4")
        create_test_video(source / "2025-10-06" / "subdir" / "test2.mp4")

        result = run_in_process(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test"],
        )

        assert "Found 2 .mp4 file(s)" in result.stderr

    def test_processes_alphabetically(self, temp_workspace, test_profile):
        """Pipeline processes files in alphabetical order."""
        source = temp_workspace["source"]
        create_test_video(source / "zebra.mp4")
        create_test_video(source / "apple.mp4")
        create_test_video(source / "mango.mp4")

        result = run_in_process(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test"],
        )

        lines = result.stderr.split("\n")
        processing_lines = [line for line in lines if "Processing:" in line]
        assert "apple.mp4" in processing_lines[0]
        assert "mango.mp4" in processing_lines[1]
        assert "zebra.mp4" in processing_lines[2]


class TestExiftoolTmpDetection:
    """Tests for stale exiftool_tmp directory detection."""

    def test_warns_about_exiftool_tmp_directories(self, temp_workspace, test_profile):
        """Pipeline warns about stale exiftool_tmp directories."""
        source = temp_workspace["source"]
        (source / "exiftool_tmp").mkdir()
        create_test_video(source / "test.mp4")

        result = run_in_process(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test"],
        )

        assert "exiftool_tmp" in result.output


@pytest.mark.skipif(sys.platform != "darwin", reason="requires macOS")
class TestStaleExiftoolTmp:
    """Stale exiftool_tmp directories must fail fast when no terminal is attached.

    The old code called input(), which under Xcode's Python opens /dev/tty even
    with stdin redirected — a non-interactive runner (tests, the app, the ralph
    loop) in a background process group then gets SIGTTIN and the entire run
    freezes instead of failing. This pins the non-interactive path: immediate
    exit 1, source untouched, no prompt wait.
    """

    def test_noninteractive_run_fails_fast_on_stale_tmp(self, temp_workspace, test_profile):
        source = temp_workspace["source"]
        create_test_video(source / "test.mp4", media_create_date="2025:10:05 01:00:00")
        stale = source / "exiftool_tmp"
        stale.mkdir()

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
        ])

        assert result.returncode == 1, "stale exiftool_tmp must abort the run"
        assert "exiftool_tmp" in result.stderr
        assert "Cannot proceed" in result.stderr
        assert stale.exists(), "non-interactive run must never delete the directories itself"


class TestIngestIntegration:
    """Tests for ingest step preserving source files."""

    def test_source_file_preserved_after_apply(self, temp_workspace, test_profile):
        """Source file remains after pipeline apply."""
        source = temp_workspace["source"]
        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:10:05 01:00:00")
        original_bytes = video.read_bytes()

        run_in_process(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test", "--apply"],
        )

        assert video.exists(), "Source file should be preserved after pipeline"
        assert video.read_bytes() == original_bytes, "Source file content should be unchanged"

    def test_source_metadata_unchanged_after_apply(self, temp_workspace, test_profile):
        """Source file metadata is not modified by pipeline apply."""
        source = temp_workspace["source"]
        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:10:05 01:00:00")

        original_dto = get_exif_field(video, "DateTimeOriginal")

        run_in_process(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test", "--apply"],
        )

        assert video.exists(), "Source file should exist"
        assert get_exif_field(video, "DateTimeOriginal") == original_dto, \
            "Source DateTimeOriginal should not be modified"
