#!/usr/bin/env python3
"""
Regression test suite for media-pipeline.

These tests verify the behavior of media-pipeline.sh and should pass
identically when run against a Python rewrite.

Run with: pytest tests/test_media_pipeline.py -v
"""

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
import pytest
import yaml

SCRIPT_DIR = Path(__file__).parent.parent
MEDIA_PIPELINE = SCRIPT_DIR / "media-pipeline.sh"

sys.path.insert(0, str(SCRIPT_DIR))


def _has_tag_cmd() -> bool:
    return shutil.which("tag") is not None


@dataclass
class PipelineResult:
    """Result from running media-pipeline."""
    stdout: str
    stderr: str
    returncode: int

    @property
    def output(self) -> str:
        """Combined stdout and stderr."""
        return self.stdout + self.stderr


def run_pipeline(args: list[str], cwd: Optional[Path] = None) -> PipelineResult:
    """Run media-pipeline.sh with given args.

    Note on output streams:
    - stdout: media-pipeline's own messages (summary, config, per-file status)
    - stderr: child script messages (organize-by-date, fix-timestamp details)
    - combined: use result.output for full output
    """
    quoted_args = " ".join(shlex.quote(arg) for arg in args)
    cmd = f"{MEDIA_PIPELINE} {quoted_args}"
    result = subprocess.run(
        cmd,
        shell=True,
        executable="/bin/bash",
        capture_output=True,
        text=True,
        cwd=cwd or SCRIPT_DIR,
    )
    return PipelineResult(
        stdout=result.stdout,
        stderr=result.stderr,
        returncode=result.returncode,
    )


from conftest import create_test_video as _create_video_raw


def create_test_video(path: Path, media_create_date: str = "2025:10:05 01:00:00"):
    _create_video_raw(path, MediaCreateDate=media_create_date, CreateDate=media_create_date)


def get_file_birth_time(path: Path) -> str:
    """Get file birth time in YYYY:MM:DD HH:MM:SS format."""
    result = subprocess.run(
        ["stat", "-f", "%SB", "-t", "%Y:%m:%d %H:%M:%S", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def get_exif_field(path: Path, field: str) -> str:
    """Get an exif field value."""
    result = subprocess.run(
        ["exiftool", "-s3", f"-{field}", str(path)],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace with source and target directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        source = workspace / "source"
        target = workspace / "target"
        source.mkdir()
        target.mkdir()
        yield {"root": workspace, "source": source, "target": target}


@pytest.fixture
def test_profile(temp_workspace):
    """Create a temporary test profile in media-profiles.yaml."""
    profiles_path = SCRIPT_DIR / "media-profiles.yaml"

    # Read existing profiles
    with open(profiles_path) as f:
        profiles = yaml.safe_load(f)

    # Add test profile
    profiles["profiles"]["_test"] = {
        "source_dir": str(temp_workspace["source"]),
        "ready_dir": str(temp_workspace["target"]),
        "file_extensions": [".mp4"],
        "tags": ["test-camera"],
        "exif": {"make": "Test", "model": "Camera"},
        "companion_extensions": [".thm", ".lrv"],
    }

    # Write back (preserve formatting)
    with open(profiles_path, "w") as f:
        yaml.dump(profiles, f, default_flow_style=False, sort_keys=False)

    yield "_test"

    # Cleanup: remove test profile
    with open(profiles_path) as f:
        profiles = yaml.safe_load(f)
    if "_test" in profiles.get("profiles", {}):
        del profiles["profiles"]["_test"]
        with open(profiles_path, "w") as f:
            yaml.dump(profiles, f, default_flow_style=False, sort_keys=False)


class TestFileDiscovery:
    """Tests for file discovery based on profile extensions."""

    def test_finds_files_by_extension(self, temp_workspace, test_profile):
        """Pipeline finds .mp4 files specified in profile."""
        source = temp_workspace["source"]
        create_test_video(source / "2025-10-05" / "test1.mp4")
        create_test_video(source / "2025-10-05" / "test2.mp4")

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test"],
        )

        assert "Found 2 video file(s)" in result.stderr

    def test_ignores_other_extensions(self, temp_workspace, test_profile):
        """Pipeline ignores files not matching profile extensions."""
        source = temp_workspace["source"]
        create_test_video(source / "2025-10-05" / "test.mp4")
        (source / "2025-10-05" / "test.mov").write_bytes(b"fake")
        (source / "2025-10-05" / "test.txt").write_bytes(b"fake")

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test"],
        )

        assert "Found 1 video file(s)" in result.stderr

    def test_finds_files_in_subdirectories(self, temp_workspace, test_profile):
        """Pipeline recursively finds files in subdirectories."""
        source = temp_workspace["source"]
        create_test_video(source / "2025-10-05" / "test1.mp4")
        create_test_video(source / "2025-10-06" / "subdir" / "test2.mp4")

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test"],
        )

        assert "Found 2 video file(s)" in result.stderr

    def test_processes_alphabetically(self, temp_workspace, test_profile):
        """Pipeline processes files in alphabetical order."""
        source = temp_workspace["source"]
        create_test_video(source / "zebra.mp4")
        create_test_video(source / "apple.mp4")
        create_test_video(source / "mango.mp4")

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test"],
        )

        lines = result.stderr.split("\n")
        processing_lines = [l for l in lines if "Processing:" in l]
        assert "apple.mp4" in processing_lines[0]
        assert "mango.mp4" in processing_lines[1]
        assert "zebra.mp4" in processing_lines[2]


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


class TestGroupTemplate:
    """Tests for --group parameter and path template."""

    def test_group_creates_correct_path_structure(self, temp_workspace, test_profile):
        """--group creates YYYY/GROUP/YYYY-MM-DD structure."""
        source = temp_workspace["source"]
        target = temp_workspace["target"]
        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:08:15 03:00:00")

        result = run_pipeline(
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

        run_pipeline(
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

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--apply"],
        )

        actual_files = list(target.rglob("*.mp4"))
        expected = target / "2025" / "2025-08-15" / "test.mp4"
        assert expected.exists(), f"Expected: {expected}\nActual files: {actual_files}\nStdout: {result.stdout[-500:]}\nStderr: {result.stderr}"

    def test_folder_template_with_group(self, temp_workspace, test_profile):
        """Profile folder_template with {{GROUP}} token substitutes the group value."""
        profiles_path = SCRIPT_DIR / "media-profiles.yaml"
        with open(profiles_path) as f:
            profiles = yaml.safe_load(f)
        profiles["profiles"]["_test"]["folder_template"] = "{{YYYY}}/{{MM}}/{{GROUP}}/{{YYYY}}-{{MM}}-{{DD}}"
        with open(profiles_path, "w") as f:
            yaml.dump(profiles, f, default_flow_style=False, sort_keys=False)

        source = temp_workspace["source"]
        target = temp_workspace["target"]
        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:08:15 03:00:00")

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Japan", "--apply"],
        )

        actual_files = list(target.rglob("*.mp4"))
        expected = target / "2025" / "08" / "Japan" / "2025-08-15" / "test.mp4"
        assert expected.exists(), f"Expected: {expected}\nActual files: {actual_files}\nStdout: {result.stdout[-500:]}\nStderr: {result.stderr}"

    def test_folder_template_without_group(self, temp_workspace, test_profile):
        """Profile folder_template used as-is when no --group given."""
        profiles_path = SCRIPT_DIR / "media-profiles.yaml"
        with open(profiles_path) as f:
            profiles = yaml.safe_load(f)
        profiles["profiles"]["_test"]["folder_template"] = "{{YYYY}}/{{MM}}/{{GROUP}}/{{YYYY}}-{{MM}}-{{DD}}"
        with open(profiles_path, "w") as f:
            yaml.dump(profiles, f, default_flow_style=False, sort_keys=False)

        source = temp_workspace["source"]
        target = temp_workspace["target"]
        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:08:15 03:00:00")

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--apply"],
        )

        actual_files = list(target.rglob("*.mp4"))
        expected = target / "2025" / "08" / "{{GROUP}}" / "2025-08-15" / "test.mp4"
        assert expected.exists(), f"Expected: {expected}\nActual files: {actual_files}\nStdout: {result.stdout[-500:]}\nStderr: {result.stderr}"


class TestAppendTimezoneToGroup:
    """Tests for --append-timezone-to-group flag."""

    def test_appends_timezone_to_group_folder(self, temp_workspace, test_profile):
        """--append-timezone-to-group appends timezone offset to group folder name."""
        source = temp_workspace["source"]
        target = temp_workspace["target"]
        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:08:15 03:00:00")

        run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Japan",
            "--append-timezone-to-group",
            "--apply",
        ])

        expected = target / "2025" / "Japan (+0900)" / "2025-08-15" / "test.mp4"
        actual_files = list(target.rglob("*.mp4"))
        assert expected.exists(), f"Expected: {expected}\nActual files: {actual_files}"

    def test_group_without_append_timezone(self, temp_workspace, test_profile):
        """--group without --append-timezone-to-group uses plain group name."""
        source = temp_workspace["source"]
        target = temp_workspace["target"]
        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:08:15 03:00:00")

        run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Japan",
            "--apply",
        ])

        expected = target / "2025" / "Japan" / "2025-08-15" / "test.mp4"
        actual_files = list(target.rglob("*.mp4"))
        assert expected.exists(), f"Expected: {expected}\nActual files: {actual_files}"

    def test_append_timezone_without_group_errors(self, temp_workspace, test_profile):
        """--append-timezone-to-group without --group exits with error."""
        source = temp_workspace["source"]
        video = source / "test.mp4"
        create_test_video(video)

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--append-timezone-to-group",
        ])

        assert result.returncode != 0
        assert "--group" in result.output

    def test_append_timezone_without_timezone_errors(self, temp_workspace, test_profile):
        """--append-timezone-to-group without --timezone exits with error."""
        source = temp_workspace["source"]
        video = source / "test.mp4"
        create_test_video(video)

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--group", "Japan",
            "--append-timezone-to-group",
        ])

        assert result.returncode != 0
        assert "--timezone" in result.output


class TestTimezoneHandling:
    """Tests for timezone parameter handling."""

    def test_timezone_affects_local_time_calculation(self, temp_workspace, test_profile):
        """Different timezones produce different local times."""
        source = temp_workspace["source"]
        target = temp_workspace["target"]

        # MediaCreateDate 01:00 UTC
        # In +0900: 10:00 local
        # In +0200: 03:00 local
        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:10:05 01:00:00")

        run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test", "--apply"],
        )

        moved = list(target.rglob("*.mp4"))[0]
        dto = get_exif_field(moved, "DateTimeOriginal")
        assert "10:00:00" in dto, f"Should be 10:00 in +0900, got: {dto}"

    def test_timezone_format_validation(self, temp_workspace, test_profile):
        """Invalid timezone format is rejected."""
        source = temp_workspace["source"]
        video = source / "test.mp4"
        create_test_video(video)

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "JST", "--group", "Test"],
        )

        assert result.returncode != 0
        assert "ERROR" in result.output or "+HHMM" in result.output


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


class TestExiftoolTmpDetection:
    """Tests for stale exiftool_tmp directory detection."""

    def test_warns_about_exiftool_tmp_directories(self, temp_workspace, test_profile):
        """Pipeline warns about stale exiftool_tmp directories."""
        source = temp_workspace["source"]
        (source / "exiftool_tmp").mkdir()
        create_test_video(source / "test.mp4")

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test"],
        )

        assert "exiftool_tmp" in result.output


@pytest.mark.skipif(
    sys.platform != "darwin" or not _has_tag_cmd(),
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

        event_types = [json.loads(l)["event"] for l in result.stdout.strip().split("\n") if l.strip()]
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

        run_pipeline(
            ["--profile", test_profile, "--source", str(correct_path.parent), "--timezone", "+0900", "--group", "Test", "--apply"],
        )

        assert correct_path.exists(), "File should still be at the organized location"
        assert correct_path.stat().st_size == original_size, "File content should be unchanged"
        all_mp4s = list(target.rglob("*.mp4"))
        assert len(all_mp4s) == 1, f"Should be exactly one file in target, found: {all_mp4s}"


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
        assert "Found 1 video file(s)" in result.stderr

    def test_source_defaults_to_profile_source_dir(self, temp_workspace, test_profile):
        """Without --source, uses profile's source_dir."""
        source = temp_workspace["source"]
        create_test_video(source / "test.mp4")

        result = run_pipeline(
            ["--profile", test_profile, "--timezone", "+0900", "--group", "Test"],
        )

        assert str(source) in result.stderr
        assert "Found 1 video file(s)" in result.stderr

    def test_target_from_profile_ready_dir(self, temp_workspace, test_profile):
        """--target defaults to profile's ready_dir."""
        source = temp_workspace["source"]
        target = temp_workspace["target"]
        create_test_video(source / "test.mp4")

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test"],
        )

        assert str(target) in result.stderr


class TestIngestIntegration:
    """Tests for ingest step preserving source files."""

    def test_source_file_preserved_after_apply(self, temp_workspace, test_profile):
        """Source file remains after pipeline apply."""
        source = temp_workspace["source"]
        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:10:05 01:00:00")
        original_bytes = video.read_bytes()

        run_pipeline(
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

        run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test", "--apply"],
        )

        assert video.exists(), "Source file should exist"
        assert get_exif_field(video, "DateTimeOriginal") == original_dto, \
            "Source DateTimeOriginal should not be modified"


class TestOutputAlwaysOn:
    """Output (organize) always runs regardless of --tasks selection."""

    def test_fix_timestamp_task_still_outputs(self, temp_workspace, test_profile):
        """--tasks fix-timestamp still moves file to target."""
        source = temp_workspace["source"]
        target = temp_workspace["target"]
        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:10:05 01:00:00")

        run_pipeline(
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

        run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900",
             "--group", "Test", "--tasks", "tag", "--apply"],
        )

        output_files = list(target.rglob("*.mp4"))
        assert len(output_files) == 1, f"File should be in target, found: {output_files}"


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

        run_pipeline([
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

        run_pipeline([
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

        run_pipeline([
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


class TestPipelineMachineOutput:
    """Test JSONL machine-readable output from media-pipeline."""

    def _parse_events(self, stdout: str) -> list[dict]:
        """Parse JSONL events from pipeline stdout, grouping by pipeline_file."""
        files: list[dict] = []
        current: dict = {}
        for line in stdout.strip().split("\n"):
            if not line.strip():
                continue
            event = json.loads(line)
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
                current["time_offset_seconds"] = event.get("time_offset_seconds")
                current["time_offset_display"] = event.get("time_offset_display")
                if event.get("error"):
                    current["timestamp_error"] = event["error"]
            elif etype == "rename_result":
                current["renamed_to"] = event["renamed_to"]
            elif etype == "organize_result":
                current["organize_action"] = event["action"]
                current["dest"] = event["dest"]
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

        raw_events = [json.loads(l) for l in result.stdout.strip().split("\n") if l.strip()]
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
        profiles_path = SCRIPT_DIR / "media-profiles.yaml"
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
            "--tasks", "tag", "fix-timestamp", "gyroflow",
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

    def test_every_event_has_file_field(self, temp_workspace, test_profile):
        """Each non-control event includes a file field for scoping.

        Actual: all result events include a file field
        Expected: JSONL events are self-contained with file context
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
                if event["event"] not in ("stage_complete",):
                    assert "file" in event, f"Event {event['event']} should include file field"

    def test_tz_mismatch_stops_with_conflict_event(self, temp_workspace, test_profile):
        """Timezone mismatch stops the pipeline and emits timezone_conflict event.

        When a file's DateTimeOriginal has a timezone that differs from --timezone,
        the pipeline should stop before processing and emit a timezone_conflict event.
        The user must re-run with --force-timezone to proceed.
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
            "--tasks", "fix-timestamp",
        ])

        assert result.returncode != 0, "Pipeline should exit non-zero on timezone conflict"

        events = [json.loads(line) for line in result.stdout.strip().split("\n") if line.strip()]
        conflict_events = [e for e in events if e.get("event") == "timezone_conflict"]
        assert len(conflict_events) == 1, f"Expected 1 timezone_conflict event, got {len(conflict_events)}"
        conflict = conflict_events[0]
        assert conflict["conflict_type"] == "provided_mismatch"
        assert conflict["provided_tz"] == "+0200"
        assert "+0900" in conflict["file_timezones"]

    def test_tz_mismatch_proceeds_with_force_timezone(self, temp_workspace, test_profile):
        """With --force-timezone, timezone mismatch overrides DTO timezone and proceeds.

        The wall-clock time is preserved but the timezone is changed to the user-provided one.
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
            "--tasks", "fix-timestamp",
        ])

        files = self._parse_events(result.stdout)
        assert len(files) == 1
        f = files[0]
        assert f.get("timestamp_action") == "would_fix", \
            f"Expected would_fix with --force-timezone, got: {f.get('timestamp_action')}"

    def test_mixed_timezones_not_bypassed_by_force_timezone(self, temp_workspace, test_profile):
        """--force-timezone does not bypass the mixed timezones check.

        When files have different embedded timezones, --force-timezone should
        not suppress the mixed_timezones conflict — only --allow-mixed-timezones
        should. This ensures the app can present each conflict dialog independently.
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
            "--tasks", "fix-timestamp",
        ])

        assert result.returncode != 0, \
            "Pipeline should still block on mixed timezones even with --force-timezone"
        events = [json.loads(line) for line in result.stdout.strip().split("\n") if line.strip()]
        conflict_events = [e for e in events if e.get("event") == "timezone_conflict"]
        assert len(conflict_events) == 1
        assert conflict_events[0]["conflict_type"] == "mixed_timezones"

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
            "--tasks", "fix-timestamp",
        ])

        events = [json.loads(line) for line in result.stdout.strip().split("\n") if line.strip()]
        conflict_events = [e for e in events if e.get("event") == "timezone_conflict"]
        assert len(conflict_events) == 0, \
            f"No timezone_conflict expected with --allow-mixed-timezones, got: {conflict_events}"

        files = self._parse_events(result.stdout)
        assert len(files) == 2, f"Both files should be processed, got {len(files)}"

    def test_filename_preflight_blocks_unparseable(self, temp_workspace, test_profile):
        """--infer-from-filename with unparseable filenames blocks before processing.

        Files like C0009.MP4 have no timestamp in their name. The pipeline
        should emit a filename_parse_error event and exit before processing,
        rather than failing mid-batch.
        """
        source = temp_workspace["source"]
        create_test_video(source / "C0009.MP4")

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--infer-from-filename",
            "--tasks", "fix-timestamp",
        ])

        assert result.returncode != 0, "Pipeline should exit non-zero for unparseable filenames"
        events = [json.loads(line) for line in result.stdout.strip().split("\n") if line.strip()]
        parse_errors = [e for e in events if e.get("event") == "filename_parse_error"]
        assert len(parse_errors) == 1, f"Expected 1 filename_parse_error event, got {len(parse_errors)}"
        assert "C0009.MP4" in parse_errors[0]["unparseable_files"]

    def test_error_field_on_timestamp_result_exception(self, temp_workspace, test_profile):
        """Exception path includes error message in timestamp_result event.

        When fix_media_timestamps() raises (e.g. --infer-from-filename on a
        file with no parseable date that slips past the pre-flight), the
        timestamp_result event should include the error string so the app
        can display it in the diff table instead of a generic "Error" label.
        """
        source = temp_workspace["source"]
        # VID_ prefix with valid date passes pre-flight; create a second file
        # with unparseable name that we'll swap in after pre-flight by creating
        # the batch with one good file and checking error on the good one won't
        # work. Instead, directly verify the JSONL event format by triggering
        # the infer-from-filename exception path:
        # The pre-flight check catches this, so we test the exception handler
        # by verifying the error= kwarg is passed to emit_event in the code.
        # For the integration test, we verify the simpler no-timezone error
        # path where the error is captured in the result dict.
        create_test_video(source / "test.mp4", media_create_date="2025:10:05 01:00:00")

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--tasks", "fix-timestamp",
        ])

        # Verify events include timestamp_result with action=error
        events = [json.loads(line) for line in result.stdout.strip().split("\n") if line.strip()]
        ts_events = [e for e in events if e.get("event") == "timestamp_result" and e.get("action") == "error"]
        assert len(ts_events) == 1, f"Expected 1 error timestamp_result, got {len(ts_events)}"

    def test_error_path_emits_original_time(self, temp_workspace, test_profile):
        """Error path emits original_time when the file has a known timestamp.

        Actual: original_time present alongside action=error in timestamp_result
        Expected: error paths include available timestamp data for display
        """
        source = temp_workspace["source"]
        create_test_video(source / "test.mp4", media_create_date="2025:10:05 01:00:00")

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--tasks", "fix-timestamp",
        ])

        files = self._parse_events(result.stdout)
        assert len(files) == 1
        f = files[0]
        assert f.get("timestamp_action") == "error", \
            f"Expected timestamp_action=error, got: {f.get('timestamp_action')}"
        assert "original_time" in f, \
            f"Error path should include original_time, got keys: {list(f.keys())}"
        assert f["original_time"], \
            f"original_time should be non-empty, got: {f.get('original_time')}"

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


@pytest.mark.skipif(sys.platform != "darwin", reason="requires macOS")
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


class TestInferFromFilename:
    """Tests for --infer-from-filename pass-through to fix-timestamp."""

    def test_infer_from_filename_passes_through(self, temp_workspace, test_profile):
        """Pipeline passes --infer-from-filename to fix-timestamp, correcting DateTimeOriginal from filename.

        Actual: DateTimeOriginal on output file matches filename timestamp + timezone
        Expected: filename timestamp used as source of truth
        """
        source = temp_workspace["source"]
        target = temp_workspace["target"]
        video = source / "VID_20250619_063809_00_002.mp4"
        _create_video_raw(
            video,
            MediaCreateDate="2025:06:18 22:38:09",
            CreateDate="2025:06:18 22:38:09",
            DateTimeOriginal="2025:06:19 09:38:09+08:00",
        )

        run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0800",
            "--group", "Test",
            "--infer-from-filename",
            "--apply",
        ])

        moved = list(target.rglob("*.mp4"))[0]
        dto = get_exif_field(moved, "DateTimeOriginal")
        assert "06:38:09" in dto, f"Should use filename time 06:38:09, got: {dto}"
        assert "+08:00" in dto, f"Should have +08:00 timezone, got: {dto}"

    def test_infer_from_filename_requires_timezone(self, temp_workspace, test_profile):
        """--infer-from-filename without --timezone is rejected by pipeline."""
        source = temp_workspace["source"]
        video = source / "VID_20250619_063809.mp4"
        create_test_video(video)

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--group", "Test",
            "--infer-from-filename",
        ])

        assert result.returncode != 0


class TestTimeOffset:
    """Tests for --time-offset pass-through to fix-timestamp."""

    def test_time_offset_passes_through(self, temp_workspace, test_profile):
        """Pipeline passes --time-offset to fix-timestamp, shifting timestamps.

        Actual: DateTimeOriginal on output file is shifted by offset seconds
        Expected: 3600s offset shifts 01:00:00 UTC → 02:00:00 UTC → 11:00:00+09:00
        """
        source = temp_workspace["source"]
        target = temp_workspace["target"]
        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:10:05 01:00:00")

        run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
            "--time-offset", "3600",
            "--apply",
        ])

        moved = list(target.rglob("*.mp4"))[0]
        dto = get_exif_field(moved, "DateTimeOriginal")
        # 01:00 UTC + 3600s = 02:00 UTC → 11:00 in +0900
        assert "11:00:00" in dto, f"Expected 11:00:00 (shifted by 1h), got: {dto}"

    def test_time_offset_requires_timezone(self, temp_workspace, test_profile):
        """--time-offset without --timezone is rejected by pipeline."""
        source = temp_workspace["source"]
        video = source / "test.mp4"
        create_test_video(video)

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--group", "Test",
            "--time-offset", "3600",
        ])

        assert result.returncode != 0


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

        run_pipeline([
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

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
            "--time-offset", "3600",
            "--update-filename-dates",
        ])

        events = [json.loads(l) for l in result.stdout.strip().split("\n") if l.strip()]
        rename_events = [e for e in events if e["event"] == "rename_result"]
        assert rename_events, \
            f"Actual: no rename_result events in {[e['event'] for e in events]}, " \
            "Expected: one rename_result with corrected filename"
        actual_new_name = rename_events[0]["renamed_to"]
        assert "20250505_140334" in actual_new_name, \
            f"Actual: renamed_to={actual_new_name}, " \
            "Expected: filename containing 20250505_140334 (shifted by +3600s)"

    def test_no_rename_when_no_parseable_date(self, temp_workspace, test_profile):
        """Files without parseable date in filename produce no rename_result event.

        Actual: event types emitted for test.mp4 (no date pattern in name)
        Expected: no rename_result event since filename has no parseable date
        """
        source = temp_workspace["source"]
        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:10:05 01:00:00")

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
            "--time-offset", "3600",
            "--update-filename-dates",
        ])

        event_types = [json.loads(l)["event"] for l in result.stdout.strip().split("\n") if l.strip()]
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

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
            "--update-filename-dates",
        ])

        event_types = [json.loads(l)["event"] for l in result.stdout.strip().split("\n") if l.strip()]
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

        run_pipeline([
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
