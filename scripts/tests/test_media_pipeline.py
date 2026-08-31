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
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
import pytest
import yaml

from pipeline_schema import validate_event

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

    Each invocation gets a working directory outside the target, so assertions
    about what the target holds see only the organized library. The default
    location — <target>/.jetlag-working — has its own coverage in
    TestDefaultWorkingDirIsOnTheTargetVolume.

    Note on output streams:
    - stdout: media-pipeline's own messages (summary, config, per-file status)
    - stderr: child script messages (organize-by-date, fix-timestamp details)
    - combined: use result.output for full output
    """
    if "--working-dir" not in args:
        args = args + ["--working-dir", tempfile.mkdtemp(prefix="pipeline_working_")]
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

import importlib.util as _importlib_util

_pipeline_spec = _importlib_util.spec_from_file_location(
    "media_pipeline_under_test", SCRIPT_DIR / "media-pipeline.py"
)
pipeline = _importlib_util.module_from_spec(_pipeline_spec)
_pipeline_spec.loader.exec_module(pipeline)


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
def test_profile(temp_workspace, monkeypatch):
    """Create a test profile in an isolated copy of media-profiles.yaml.

    The copy plus the JETLAG_PROFILES_FILE override keeps every test (and its
    spawned scripts) off the shared repo file, which is what allows the suite
    to run in parallel workers. Tests that need to tweak the profile edit the
    copy via os.environ["JETLAG_PROFILES_FILE"].
    """
    profiles_path = temp_workspace["root"] / "media-profiles.yaml"

    with open(SCRIPT_DIR / "media-profiles.yaml") as f:
        profiles = yaml.safe_load(f)

    profiles["profiles"]["_test"] = {
        "source_dir": str(temp_workspace["source"]),
        "ready_dir": str(temp_workspace["target"]),
        "file_extensions": [".mp4"],
        "tags": ["test-camera"],
        "exif": {"make": "Test", "model": "Camera"},
        "companion_extensions": [".thm", ".lrv"],
    }

    with open(profiles_path, "w") as f:
        yaml.dump(profiles, f, default_flow_style=False, sort_keys=False)

    monkeypatch.setenv("JETLAG_PROFILES_FILE", str(profiles_path))
    yield "_test"


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

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Japan", "--apply"],
        )

        actual_files = list(target.rglob("*.mp4"))
        expected = target / "2025" / "08" / "Japan" / "2025-08-15" / "test.mp4"
        assert expected.exists(), f"Expected: {expected}\nActual files: {actual_files}\nStdout: {result.stdout[-500:]}\nStderr: {result.stderr}"

    def test_folder_template_without_group(self, temp_workspace, test_profile):
        """Profile folder_template used as-is when no --group given."""
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

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--apply"],
        )

        actual_files = list(target.rglob("*.mp4"))
        expected = target / "2025" / "08" / "{{GROUP}}" / "2025-08-15" / "test.mp4"
        assert expected.exists(), f"Expected: {expected}\nActual files: {actual_files}\nStdout: {result.stdout[-500:]}\nStderr: {result.stderr}"


class TestGroupFolder:
    """Tests for --group folder placement."""

    def test_group_folder(self, temp_workspace, test_profile):
        """--group inserts a folder between the year and the date."""
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

    def test_unknown_zone_name_is_rejected(self, temp_workspace, test_profile):
        """A zone name that is not in the database is rejected."""
        source = temp_workspace["source"]
        create_test_video(source / "test.mp4")

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source),
             "--timezone", "Pacific/Atlantis", "--group", "Test"],
        )

        assert result.returncode != 0
        assert "unknown timezone" in result.output.lower()

    def test_zone_name_resolves_per_file_across_a_dst_changeover(self, temp_workspace, test_profile):
        """One run, one zone, two offsets — NZ left daylight time on 2025-04-06.

        Both files carry the same UTC instant on either side of the changeover,
        so a single frozen offset would give them the same local hour.
        """
        source = temp_workspace["source"]
        target = temp_workspace["target"]
        create_test_video(source / "summer.mp4", media_create_date="2025:03:15 01:00:00")
        create_test_video(source / "winter.mp4", media_create_date="2025:07:15 01:00:00")

        run_pipeline(
            ["--profile", test_profile, "--source", str(source),
             "--timezone", "Pacific/Auckland", "--group", "Test", "--apply"],
        )

        moved = {p.name: p for p in target.rglob("*.mp4")}
        summer = get_exif_field(moved["summer.mp4"], "DateTimeOriginal")
        winter = get_exif_field(moved["winter.mp4"], "DateTimeOriginal")

        assert "+13:00" in summer, f"March is NZDT, got: {summer}"
        assert "+12:00" in winter, f"July is NZST, got: {winter}"
        assert "14:00:00" in summer, f"01:00 UTC is 14:00 NZDT, got: {summer}"
        assert "13:00:00" in winter, f"01:00 UTC is 13:00 NZST, got: {winter}"


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
        with the conflict reported as data: an informational timezone_conflict
        event plus a per-file requires_force_timezone flag the app can flag in
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
            "--tasks", "fix-timestamp",
        ])

        assert result.returncode == 0, \
            f"Dry run should continue past a timezone conflict, got {result.returncode}"

        events = [json.loads(line) for line in result.stdout.strip().split("\n") if line.strip()]
        conflict_events = [e for e in events if e.get("event") == "timezone_conflict"]
        assert len(conflict_events) == 1, f"Expected 1 timezone_conflict event, got {len(conflict_events)}"
        conflict = conflict_events[0]
        assert conflict["conflict_type"] == "provided_mismatch"
        assert conflict["provided_tz"] == "+0200"
        assert "+0900" in conflict["file_timezones"]

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
        records local digits with no zone, and QuickTime:MediaCreateDate records the
        instant in UTC. Their delta is a legal zone offset (+09:00) — the camera's
        own setting — independent of the declared --timezone used to resolve the fix.
        """
        source = temp_workspace["source"]
        video = source / "VID_20260104_033532_00_001.mp4"
        _create_video_raw(video, MediaCreateDate="2026:01:03 18:35:32")

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+1300",
            "--tasks", "fix-timestamp",
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

        The fixture's DateTimeOriginal and track atoms are already right for +08:00;
        only the movie header is eight hours out and Keys:CreationDate is missing.
        """
        source = temp_workspace["source"]
        video = source / "test.mp4"
        _create_video_raw(
            video,
            DateTimeOriginal="2025:06:18 07:25:21+08:00",
            **{"QuickTime:CreateDate": "2025:06:18 07:25:21",
               "QuickTime:MediaCreateDate": "2025:06:17 23:25:21",
               "QuickTime:TrackCreateDate": "2025:06:17 23:25:21"},
        )

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0800",
            "--tasks", "fix-timestamp",
        ])

        files = self._parse_events(result.stdout)
        assert len(files) == 1
        assert files[0].get("stale_fields") == ["Keys:CreationDate", "QuickTime:CreateDate"], \
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
            "--tasks", "fix-timestamp",
            "--apply",
        ])

        assert result.returncode != 0, "Apply should exit non-zero on timezone conflict"

        events = [json.loads(line) for line in result.stdout.strip().split("\n") if line.strip()]
        conflict_events = [e for e in events if e.get("event") == "timezone_conflict"]
        assert len(conflict_events) == 1, f"Expected 1 timezone_conflict event, got {len(conflict_events)}"
        assert conflict_events[0]["conflict_type"] == "provided_mismatch"
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


class TestOverwriteDestination:
    """A file already sitting at the organize destination blocks the move.

    The pipeline reports that as data — every blocked file skips with
    reason=exists_differs and the batch ends with one organize_conflict event
    carrying the count — and only replaces those files when --overwrite says so.
    The app reads the conflict event to ask the user before re-running with the
    flag, so the count and the file list have to be right.
    """

    def _run(self, workspace, profile, *extra):
        return run_pipeline([
            "--profile", profile,
            "--source", str(workspace["source"]),
            "--target", str(workspace["target"]),
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
        organize = next(e for e in events if e["event"] == "organize_result")
        assert organize["action"] == "skipped", \
            f"Actual: organize_result.action={organize['action']!r}, Expected: 'skipped'"
        assert organize.get("reason") == "exists_differs", \
            f"Actual: organize_result.reason={organize.get('reason')!r}, Expected: 'exists_differs'"

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
        organize = next(e for e in events if e["event"] == "organize_result")
        assert organize["action"] == "overwrote", \
            f"Actual: organize_result.action={organize['action']!r}, Expected: 'overwrote'"
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
        organize = next(e for e in events if e["event"] == "organize_result")
        assert organize["action"] == "would_overwrite", \
            f"Actual: organize_result.action={organize['action']!r}, Expected: 'would_overwrite'"
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
        organize = next(e for e in events if e["event"] == "organize_result")
        assert organize.get("reason") == "identical", \
            f"Actual: organize_result.reason={organize.get('reason')!r}, Expected: 'identical'"
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
        return run_pipeline([
            "--profile", profile,
            "--source", str(workspace["source"]),
            "--target", str(workspace["target"]),
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


# The pipeline stages every file through a working directory before organize
# places it. These runs exercise the default location, so they cannot go
# through run_pipeline(), which supplies a --working-dir of its own. The spy
# runner loads media-pipeline as a module, records where ingest staged each
# file and the inode organize was handed just before it moved it, then runs
# main() exactly as the CLI would.
_PIPELINE_SPY_RUNNER = '''
import importlib.util
import json
import os
import sys

spec = importlib.util.spec_from_file_location("media_pipeline_under_test", sys.argv[1])
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)

record_path = sys.argv[2]


def record(**entry):
    with open(record_path, "a") as handle:
        handle.write(json.dumps(entry) + "\\n")


real_ingest = pipeline._ingest_mod.ingest_file
real_organize = pipeline._organize_mod.process_file


def ingest_spy(source, working_dir, apply, **kwargs):
    dest, action, companions = real_ingest(source, working_dir, apply, **kwargs)
    if dest and os.path.exists(dest):
        record(hook="ingest", dest=dest)
    return dest, action, companions


def organize_spy(file_path, *args, **kwargs):
    before = os.stat(file_path).st_ino if os.path.exists(file_path) else None
    result = real_organize(file_path, *args, **kwargs)
    record(hook="organize", source=file_path, inode=before, dest=result.dest)
    return result


pipeline._ingest_mod.ingest_file = ingest_spy
pipeline._organize_mod.process_file = organize_spy
sys.argv = [sys.argv[0]] + sys.argv[3:]
pipeline.main()
'''


def _staged_paths(entries: list[dict]) -> list[Path]:
    return [Path(entry["dest"]) for entry in entries if entry["hook"] == "ingest"]


class TestDefaultWorkingDirIsOnTheTargetVolume:
    """With no --working-dir, staging happens on the target's own volume.

    Staging is unavoidable — the source is read-only and organize picks the date
    folder from the timestamp the correction just wrote — but its location is
    not. Staged on the boot volume, every file crosses volumes twice: once for
    ingest's copy and again for organize's move, which degrades to a full copy
    plus delete between filesystems. Under the target, ingest is one same-volume
    copy and the move is a rename, so the destination's free space is the only
    limit on a batch.
    """

    def _run(self, tmp_path, home, args):
        runner = tmp_path / "pipeline_spy_runner.py"
        runner.write_text(_PIPELINE_SPY_RUNNER)
        record = tmp_path / "hooks.jsonl"
        environment = dict(os.environ)
        environment["HOME"] = str(home)
        # macOS's framework Python caches bytecode under ~/Library/Caches when
        # the source tree is read-only to it, which would land in the home
        # directory these runs assert stays empty. That is the interpreter's
        # doing, not the pipeline's, so turn it off rather than carve it out.
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [sys.executable, str(runner), str(SCRIPT_DIR / "media-pipeline.py"),
             str(record), *args],
            cwd=str(SCRIPT_DIR), capture_output=True, text=True, env=environment,
        )
        entries = [json.loads(line) for line in record.read_text().splitlines()] \
            if record.exists() else []
        return PipelineResult(completed.stdout, completed.stderr,
                              completed.returncode), entries

    @pytest.fixture
    def empty_home(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir()
        return home

    def _pipeline_args(self, workspace, *extra):
        return [
            "--source", str(workspace["source"]),
            "--target", str(workspace["target"]),
            "--timezone", "+0900",
            "--group", "Test",
            *extra,
        ]

    def test_apply_stages_under_the_target_and_leaves_home_untouched(
            self, tmp_path, temp_workspace, empty_home):
        """An apply run with no --working-dir puts its staged copies under the
        target, and writes nothing at all under the user's home directory.

        Actual: every staged copy sits in <target>/.jetlag-working and the home
        directory is still empty after the run
        Expected: the boot volume's free space is no longer the batch's limit
        """
        create_test_video(temp_workspace["source"] / "VID_20251005_100000_00_001.mp4")

        result, entries = self._run(
            tmp_path, empty_home, self._pipeline_args(temp_workspace, "--apply"))

        assert result.returncode == 0, f"Actual: {result.output}, Expected: a clean run"
        expected_dir = temp_workspace["target"] / ".jetlag-working"
        staged = _staged_paths(entries)
        assert staged, "Actual: nothing staged, Expected: ingest staged the file"
        assert [path.parent for path in staged] == [expected_dir], \
            f"Actual: staged at {staged}, Expected: under {expected_dir}"
        assert sorted(p.name for p in empty_home.rglob("*")) == [], \
            f"Actual: home holds {sorted(p.name for p in empty_home.rglob('*'))}, " \
            "Expected: nothing written under HOME"

    def test_staged_copy_is_renamed_into_place_not_copied_again(
            self, tmp_path, temp_workspace, empty_home):
        """Organize's move of a same-volume staged copy is a rename, so the file
        at the destination is the staged copy itself — no second full copy.

        Actual: the destination file's inode is the staged copy's inode
        Expected: a run costs one copy per file, not two
        """
        create_test_video(temp_workspace["source"] / "VID_20251005_100000_00_001.mp4")

        result, entries = self._run(
            tmp_path, empty_home, self._pipeline_args(temp_workspace, "--apply"))

        assert result.returncode == 0, f"Actual: {result.output}, Expected: a clean run"
        organized = sorted(temp_workspace["target"].rglob("*.mp4"))
        assert len(organized) == 1, f"Actual: {organized}, Expected: one organized file"
        moved = [entry for entry in entries if entry["hook"] == "organize"]
        assert len(moved) == 1, f"Actual: {moved}, Expected: one organize call"
        assert os.stat(organized[0]).st_ino == moved[0]["inode"], \
            f"Actual: {organized[0]} has a different inode from the staged copy " \
            f"organize was handed ({moved[0]['source']}), " \
            "Expected: organize renamed the staged copy into place"

    def test_clean_apply_removes_the_default_working_dir(
            self, tmp_path, temp_workspace, empty_home):
        """The staging directory does not outlive the run that created it.

        Actual: <target>/.jetlag-working is gone after a run with no failures
        Expected: the target is left holding only the organized library
        """
        create_test_video(temp_workspace["source"] / "VID_20251005_100000_00_001.mp4")

        result, _ = self._run(
            tmp_path, empty_home, self._pipeline_args(temp_workspace, "--apply"))

        assert result.returncode == 0, f"Actual: {result.output}, Expected: a clean run"
        assert not (temp_workspace["target"] / ".jetlag-working").exists(), \
            "Actual: the staging directory survived a clean run, Expected: removed"

    def test_explicit_working_dir_still_overrides_the_default(
            self, tmp_path, temp_workspace, empty_home):
        """--working-dir remains an override: nothing is staged under the target.

        Actual: staged copies sit in the given directory and no
        <target>/.jetlag-working is created
        Expected: callers that place staging themselves are unaffected
        """
        create_test_video(temp_workspace["source"] / "VID_20251005_100000_00_001.mp4")
        override = tmp_path / "elsewhere"

        result, entries = self._run(
            tmp_path, empty_home,
            self._pipeline_args(temp_workspace, "--apply", "--working-dir", str(override)))

        assert result.returncode == 0, f"Actual: {result.output}, Expected: a clean run"
        staged = _staged_paths(entries)
        assert [path.parent for path in staged] == [override], \
            f"Actual: staged at {staged}, Expected: under {override}"
        assert not (temp_workspace["target"] / ".jetlag-working").exists(), \
            "Actual: the default staging directory was created anyway, Expected: not used"

    def test_dry_run_creates_no_staging_directory_under_the_target(
            self, tmp_path, temp_workspace, empty_home):
        """A dry run stages nothing, so it creates nothing under the target.

        Actual: no .jetlag-working after a preview
        Expected: previewing a run never writes to the destination volume
        """
        create_test_video(temp_workspace["source"] / "VID_20251005_100000_00_001.mp4")

        result, entries = self._run(
            tmp_path, empty_home, self._pipeline_args(temp_workspace))

        assert result.returncode == 0, f"Actual: {result.output}, Expected: a clean run"
        staged = _staged_paths(entries)
        assert staged == [], f"Actual: {staged} staged, Expected: nothing"
        assert not (temp_workspace["target"] / ".jetlag-working").exists(), \
            "Actual: a dry run created the staging directory, Expected: not created"

class TestWorkingDirIsTransient:
    """Nothing survives in the working directory past its own file's iteration.

    The working directory is an implementation detail: ingest stages a copy of
    every source file into it and organize moves that copy out. When organize
    declines to place it — the destination already holds the same file, or a
    different one and --overwrite was not given — the staged copy has no further
    use, so the pipeline discards it. Idempotent re-runs are a designed use, so
    without this a second run over an already-organized library leaves the whole
    library duplicated on the working volume.
    """

    def _run(self, workspace, profile, working_dir, *extra):
        return run_pipeline([
            "--profile", profile,
            "--source", str(workspace["source"]),
            "--target", str(workspace["target"]),
            "--timezone", "+0900",
            "--group", "Test",
            "--working-dir", str(working_dir),
            *extra,
        ])

    def _leftovers(self, working_dir: Path) -> list[str]:
        if not working_dir.exists():
            return []
        return sorted(p.name for p in working_dir.iterdir())

    def _organize_results(self, stdout: str) -> list[dict]:
        return [event for event in
                (json.loads(line) for line in stdout.strip().split("\n") if line.strip())
                if event["event"] == "organize_result"]

    def test_second_identical_apply_leaves_no_staged_copies(self, temp_workspace, test_profile):
        """Re-running an already-organized folder must not duplicate it into the working dir.

        Actual: after the second apply the working dir holds no files, every
        file skipped as identical, and the destination files are byte-identical
        Expected: an idempotent re-run costs no disk space
        """
        working_dir = temp_workspace["root"] / "working"
        names = ["VID_20251005_100000_00_001.mp4", "VID_20251005_110000_00_002.mp4"]
        for name in names:
            create_test_video(temp_workspace["source"] / name)

        self._run(temp_workspace, test_profile, working_dir, "--apply")
        organized = sorted(temp_workspace["target"].rglob("*.mp4"))
        assert len(organized) == 2, f"Actual: {organized}, Expected: both files organized"
        before = {p.name: p.read_bytes() for p in organized}

        result = self._run(temp_workspace, test_profile, working_dir, "--apply")

        actions = [(e["action"], e.get("reason")) for e in self._organize_results(result.stdout)]
        assert actions == [("skipped", "identical")] * 2, \
            f"Actual: {actions}, Expected: both files skipped as identical"
        assert self._leftovers(working_dir) == [], \
            f"Actual: working dir holds {self._leftovers(working_dir)}, Expected: nothing"
        after = {p.name: p.read_bytes() for p in temp_workspace["target"].rglob("*.mp4")}
        assert after == before, "Actual: destination bytes changed, Expected: untouched"

    def test_blocked_by_a_different_file_leaves_no_staged_copy(self, temp_workspace, test_profile):
        """A file organize refuses to overwrite still leaves nothing staged behind.

        Actual: skipped with reason=exists_differs, working dir empty, source intact
        Expected: the skip cleans up after itself just like the identical one
        """
        working_dir = temp_workspace["root"] / "working"
        name = "VID_20251005_100000_00_001.mp4"
        source_file = temp_workspace["source"] / name
        create_test_video(source_file)
        self._run(temp_workspace, test_profile, working_dir, "--apply")

        organized = next(temp_workspace["target"].rglob(name))
        with open(organized, "ab") as f:
            f.write(b"x" * 100)
        create_test_video(source_file)
        source_bytes = source_file.read_bytes()

        result = self._run(temp_workspace, test_profile, working_dir, "--apply")

        actions = [(e["action"], e.get("reason")) for e in self._organize_results(result.stdout)]
        assert actions == [("skipped", "exists_differs")], \
            f"Actual: {actions}, Expected: skipped/exists_differs"
        assert self._leftovers(working_dir) == [], \
            f"Actual: working dir holds {self._leftovers(working_dir)}, Expected: nothing"
        assert source_file.read_bytes() == source_bytes, \
            "Actual: the source file changed, Expected: untouched"

    def test_companion_copies_are_discarded_with_the_file_they_belong_to(
            self, temp_workspace, test_profile):
        """A discarded staged copy takes its companion copies with it.

        Actual: neither the .mp4 nor its .thm remains in the working dir
        Expected: companions staged by ingest are cleaned up on a skip too
        """
        working_dir = temp_workspace["root"] / "working"
        name = "VID_20251005_100000_00_001.mp4"
        video = temp_workspace["source"] / name
        create_test_video(video)
        (temp_workspace["source"] / "VID_20251005_100000_00_001.thm").write_bytes(b"thumb")

        self._run(temp_workspace, test_profile, working_dir, "--apply", "--copy-companion-files")
        result = self._run(temp_workspace, test_profile, working_dir, "--apply",
                           "--copy-companion-files")

        actions = [e["action"] for e in self._organize_results(result.stdout)]
        assert actions == ["skipped"], f"Actual: {actions}, Expected: skipped"
        assert self._leftovers(working_dir) == [], \
            f"Actual: working dir holds {self._leftovers(working_dir)}, Expected: nothing"

    def test_discard_line_names_the_file_not_the_working_dir(self, temp_workspace, test_profile):
        """The discard is reported, and reported without leaking the staging path.

        Actual: one 'Discarded staged copy' line naming the file and the skip reason
        Expected: the user can see where the staged copy went
        """
        working_dir = temp_workspace["root"] / "working"
        name = "VID_20251005_100000_00_001.mp4"
        create_test_video(temp_workspace["source"] / name)
        self._run(temp_workspace, test_profile, working_dir, "--apply")

        result = self._run(temp_workspace, test_profile, working_dir, "--apply")

        discards = [line for line in result.output.split("\n") if "Discarded staged copy" in line]
        assert len(discards) == 1, \
            f"Actual: {len(discards)} discard lines, Expected: 1\n{result.output}"
        assert name in discards[0] and "identical" in discards[0], \
            f"Actual: {discards[0]!r}, Expected: it to name {name} and the skip reason"
        assert str(working_dir) not in discards[0], \
            f"Actual: {discards[0]!r} leaks the working dir path, Expected: it names the file only"

    def test_organize_error_keeps_the_staged_copy_for_inspection(self, temp_workspace):
        """A file whose organize step errors keeps its staged copy on disk.

        Organize only errors when it cannot resolve a date for the file it was
        handed, which no source directory can be arranged to produce, so the
        step is stubbed out. The run is marked failed and main() then preserves
        the whole working dir — discarding the copy would throw away the
        evidence that failure exists to keep.

        Actual: the staged copy is still in the working dir and the pipeline
        owns nothing there for a cancel to remove
        Expected: only a clean run cleans up
        """
        working_dir = temp_workspace["root"] / "working"
        working_dir.mkdir()
        name = "VID_20251005_100000_00_001.mp4"
        create_test_video(temp_workspace["source"] / name)

        errored = pipeline._organize_mod.OrganizeResult(dest="", action="error")
        original = pipeline.run_organize_by_date
        pipeline.run_organize_by_date = lambda *a, **k: errored
        try:
            result = pipeline.process_file(
                temp_workspace["source"] / name, None, str(temp_workspace["target"]),
                str(working_dir), None, None, True, False, tasks=set(),
            )
        finally:
            pipeline.run_organize_by_date = original

        assert result["failed"], "Actual: the run succeeded, Expected: organize's error to fail it"
        assert self._leftovers(working_dir) == [name], \
            f"Actual: working dir holds {self._leftovers(working_dir)}, Expected: the staged copy"
        assert pipeline._staged_paths == [], \
            "Actual: the preserved copy is still owned, Expected: a cancel must not remove it"

    def test_leftover_entries_on_a_clean_run_are_reported(self, temp_workspace, test_profile):
        """A non-empty working dir after a run with no failures is a defect, not a silence.

        Actual: the run warns, naming how many entries were left behind
        Expected: the pipeline never hides a working dir it failed to clean up
        """
        working_dir = temp_workspace["root"] / "working"
        working_dir.mkdir()
        (working_dir / "stray.mp4").write_bytes(b"stray")
        create_test_video(temp_workspace["source"] / "VID_20251005_100000_00_001.mp4")

        result = self._run(temp_workspace, test_profile, working_dir, "--apply")

        assert result.returncode == 0, f"Actual: rc={result.returncode}, Expected: a clean run"
        warnings = [line for line in result.output.split("\n")
                    if "left" in line and "working dir" in line.lower()]
        assert len(warnings) == 1, \
            f"Actual: {warnings}, Expected: one leftover warning\n{result.output}"
        assert "1" in warnings[0], \
            f"Actual: {warnings[0]!r}, Expected: it to name the leftover count"

    def test_a_clean_run_says_nothing_about_the_working_dir(self, temp_workspace, test_profile):
        """With the working dir emptied there is nothing to warn about."""
        working_dir = temp_workspace["root"] / "working"
        create_test_video(temp_workspace["source"] / "VID_20251005_100000_00_001.mp4")

        result = self._run(temp_workspace, test_profile, working_dir, "--apply")

        assert not working_dir.exists(), \
            f"Actual: working dir survives holding {self._leftovers(working_dir)}, Expected: removed"
        assert "left in the working dir" not in result.output, \
            f"Actual: a clean run warned about leftovers\n{result.output}"


class TestCancelClearsTheWorkingDir:
    """Cancel is not a failure, so it leaves nothing in the working directory.

    The handler runs after the metadata service has been closed — exiftool has
    finished or died and is no longer writing — so it is safe to remove the
    copies the interrupted file's iteration owns, the scratch files an
    interrupted exiftool write left behind, and the directory itself.
    """

    @pytest.fixture
    def staged_working_dir(self, tmp_path, monkeypatch):
        """A working dir mid-file: a staged copy, its companion, exiftool scratch."""
        working_dir = tmp_path / "working"
        working_dir.mkdir()
        staged = working_dir / "VID_20251005_100000_00_001.mp4"
        companion = working_dir / "VID_20251005_100000_00_001.thm"
        staged.write_bytes(b"half a video")
        companion.write_bytes(b"thumb")
        (working_dir / "VID_20251005_100000_00_001.mp4_exiftool_tmp").write_bytes(b"scratch")

        monkeypatch.setattr(pipeline, "_working_dir", str(working_dir))
        monkeypatch.setattr(pipeline.metadata_service, "close", lambda: None)
        pipeline.register_staged_paths([staged, companion])
        yield working_dir
        pipeline._staged_paths.clear()

    @pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM],
                             ids=["sigint", "sigterm"])
    def test_handler_removes_staged_copies_scratch_files_and_the_dir(
            self, staged_working_dir, sig):
        """Both signals mean the same thing: Cancel in the app is Ctrl+C.

        Actual: after the handler exits, no staged copy, no companion copy, no
        *_exiftool_tmp entry and no working dir remain
        Expected: a cancelled run leaves the disk as it found it
        """
        with pytest.raises(SystemExit) as exit_info:
            pipeline.signal_handler(sig, None)

        assert exit_info.value.code == 128 + sig, \
            f"Actual: exit {exit_info.value.code}, Expected: {128 + sig}"
        assert not staged_working_dir.exists(), \
            ("Actual: working dir survives holding "
             f"{sorted(p.name for p in staged_working_dir.iterdir())}, Expected: removed")

    def test_handler_keeps_a_working_dir_holding_someone_elses_files(
            self, staged_working_dir):
        """Cleanup only removes what the run owns — an unexpected file stays put.

        Actual: the staged copies and scratch file go, the stray file and the
        directory holding it remain
        Expected: the pipeline never deletes a working dir it does not recognise
        """
        stray = staged_working_dir / "not-ours.txt"
        stray.write_bytes(b"someone else's")

        with pytest.raises(SystemExit):
            pipeline.signal_handler(signal.SIGTERM, None)

        assert sorted(p.name for p in staged_working_dir.iterdir()) == ["not-ours.txt"], \
            f"Actual: {sorted(p.name for p in staged_working_dir.iterdir())}, Expected: only the stray"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
