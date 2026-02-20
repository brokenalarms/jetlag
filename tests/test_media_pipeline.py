#!/usr/bin/env python3
"""
Regression test suite for media-pipeline.

These tests verify the behavior of media-pipeline.sh and should pass
identically when run against a Python rewrite.

Run with: pytest tests/test_media_pipeline.py -v
"""

import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import pytest
import yaml

SCRIPT_DIR = Path(__file__).parent.parent / "scripts"
MEDIA_PIPELINE = SCRIPT_DIR / "media-pipeline.sh"
VENV_ACTIVATE = SCRIPT_DIR / "media-import" / "bin" / "activate"


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
    cmd = f"source {VENV_ACTIVATE} && {MEDIA_PIPELINE} {quoted_args}"
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


def create_test_video(path: Path, media_create_date: str = "2025:10:05 01:00:00"):
    """Create a minimal test video file with exif metadata using ffmpeg."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Create a minimal valid MP4 using ffmpeg (1 frame, tiny resolution)
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=16x16:d=0.04",
            "-c:v", "libx264", "-t", "0.04", str(path)
        ],
        capture_output=True,
        check=True,
    )
    # Set MediaCreateDate and CreateDate
    subprocess.run(
        [
            "exiftool", "-overwrite_original",
            f"-MediaCreateDate={media_create_date}",
            f"-CreateDate={media_create_date}",
            str(path)
        ],
        capture_output=True,
        check=True,
    )


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
        "import_dir": str(temp_workspace["source"]),
        "ready_dir": str(temp_workspace["target"]),
        "file_extensions": [".mp4"],
        "tags": ["test-camera"],
        "exif": {"make": "Test", "model": "Camera"},
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

        assert "Found 2 video file(s)" in result.stdout

    def test_ignores_other_extensions(self, temp_workspace, test_profile):
        """Pipeline ignores files not matching profile extensions."""
        source = temp_workspace["source"]
        create_test_video(source / "2025-10-05" / "test.mp4")
        (source / "2025-10-05" / "test.mov").write_bytes(b"fake")
        (source / "2025-10-05" / "test.txt").write_bytes(b"fake")

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test"],
        )

        assert "Found 1 video file(s)" in result.stdout

    def test_finds_files_in_subdirectories(self, temp_workspace, test_profile):
        """Pipeline recursively finds files in subdirectories."""
        source = temp_workspace["source"]
        create_test_video(source / "2025-10-05" / "test1.mp4")
        create_test_video(source / "2025-10-06" / "subdir" / "test2.mp4")

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test"],
        )

        assert "Found 2 video file(s)" in result.stdout

    def test_processes_alphabetically(self, temp_workspace, test_profile):
        """Pipeline processes files in alphabetical order."""
        source = temp_workspace["source"]
        create_test_video(source / "zebra.mp4")
        create_test_video(source / "apple.mp4")
        create_test_video(source / "mango.mp4")

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test"],
        )

        lines = result.stdout.split("\n")
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

        assert not video.exists(), "Source file should be moved"
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

        # Debug: show what happened
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

        assert "Total files processed: 3" in result.stdout
        assert "Successfully completed: 3" in result.stdout

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

        assert "Failed: 1" in result.stdout or result.returncode != 0


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

        # Check that tagging was reported in output (Spotlight indexing unreliable in temp dirs)
        assert "Tagged:" in result.stdout or "Already tagged" in result.stdout

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
        """Files already in correct location are skipped."""
        target = temp_workspace["target"]
        # Create file already in the correct organized location
        correct_path = target / "2025" / "Test" / "2025-10-05" / "test.mp4"
        create_test_video(correct_path, media_create_date="2025:10:05 01:00:00")
        # Set DateTimeOriginal so it's "complete"
        subprocess.run(
            ["exiftool", "-overwrite_original", "-DateTimeOriginal=2025:10:05 10:00:00+09:00", str(correct_path)],
            capture_output=True,
        )

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(correct_path.parent), "--timezone", "+0900", "--group", "Test", "--apply"],
        )

        assert "Already organized" in result.output or "No change" in result.output


class TestCLIArguments:
    """Tests for CLI argument handling."""

    def test_requires_group_argument(self, temp_workspace, test_profile):
        """--group is required."""
        source = temp_workspace["source"]
        create_test_video(source / "test.mp4")

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900"],
        )

        assert result.returncode != 0
        assert "--group" in result.output or "required" in result.output.lower()

    def test_source_defaults_to_profile_import_dir(self, temp_workspace, test_profile):
        """Without --source, uses profile's import_dir."""
        source = temp_workspace["source"]
        create_test_video(source / "test.mp4")

        result = run_pipeline(
            ["--profile", test_profile, "--timezone", "+0900", "--group", "Test"],
        )

        assert str(source) in result.stdout
        assert "Found 1 video file(s)" in result.stdout

    def test_target_from_profile_ready_dir(self, temp_workspace, test_profile):
        """--target defaults to profile's ready_dir."""
        source = temp_workspace["source"]
        target = temp_workspace["target"]
        create_test_video(source / "test.mp4")

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test"],
        )

        assert str(target) in result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
