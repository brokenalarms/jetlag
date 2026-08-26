#!/usr/bin/env python3
"""
Tests for fix-media-timestamp.py
Validates timestamp fixing behavior, idempotency, and edge cases
"""

import os
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path
import pytest

from conftest import create_test_video


FIXTURES_DIR = Path(__file__).parent / "fixtures"
SCRIPT_DIR = Path(__file__).parent.parent


def _parse_at_lines(stdout: str) -> dict:
    """Parse @@key=value lines from stdout."""
    result = {}
    for line in stdout.strip().split("\n"):
        if line.startswith("@@"):
            key_value = line[2:]
            if "=" in key_value:
                key, value = key_value.split("=", 1)
                result[key] = value
    return result


class TestFixMediaTimestamp:
    """Test suite for fix-media-timestamp.py"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files"""
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        shutil.rmtree(tmpdir)

    @pytest.fixture
    def test_video(self, temp_dir):
        """Create a test video file with known metadata"""
        video_path = os.path.join(temp_dir, "test_video.mp4")
        create_test_video(video_path, DateTimeOriginal="2025:06:18 07:25:21+08:00")
        return video_path

    @pytest.fixture
    def test_video_no_timezone(self, temp_dir):
        """Create test video with DateTimeOriginal but no timezone"""
        video_path = os.path.join(temp_dir, "test_no_tz.mp4")
        create_test_video(video_path, DateTimeOriginal="2025:06:18 07:25:21")
        return video_path

    def test_dry_run_no_changes(self, test_video):
        """Test that dry run doesn't modify files"""
        original_mtime = os.stat(test_video).st_mtime

        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            test_video, "--timezone", "+08:00"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        assert "(DRY RUN)" in result.stderr

        assert os.stat(test_video).st_mtime == original_mtime

    def test_idempotency(self, test_video):
        """Test that running twice doesn't change anything the second time"""
        result1 = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            test_video, "--timezone", "+08:00", "--apply"
        ], capture_output=True, text=True)

        assert result1.returncode == 0

        # Verify EXIF was written after first run
        exif_result = subprocess.run([
            "exiftool", "-s", "-Keys:CreationDate", test_video
        ], capture_output=True, text=True, check=True)
        assert "+08:00" in exif_result.stdout

        # Second run should report "No change"
        result2 = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            test_video, "--timezone", "+08:00", "--apply"
        ], capture_output=True, text=True)

        assert result2.returncode == 0
        assert "No change" in result2.stderr

    def test_timezone_flag(self, test_video_no_timezone):
        """Test --timezone flag adds timezone to DateTimeOriginal without timezone"""
        # File has DateTimeOriginal but no timezone - should add it
        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            test_video_no_timezone,
            "--timezone", "+0800",
            "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0

        # Verify Keys:CreationDate was written with timezone
        exif_result = subprocess.run([
            "exiftool", "-s", "-Keys:CreationDate", test_video_no_timezone
        ], capture_output=True, text=True, check=True)

        # Should have timezone added
        assert "CreationDate" in exif_result.stdout
        assert "+08:00" in exif_result.stdout

    def test_keys_creationdate_updated(self, test_video):
        """Test that Keys:CreationDate is written correctly"""
        # Run with --apply
        subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            test_video, "--timezone", "+08:00", "--apply"
        ], capture_output=True, check=True)

        # Read Keys:CreationDate
        result = subprocess.run([
            "exiftool", "-s", "-Keys:CreationDate", test_video
        ], capture_output=True, text=True, check=True)

        # Should have Keys:CreationDate set
        assert "CreationDate" in result.stdout
        assert "+08:00" in result.stdout  # Should preserve timezone

    def test_filename_pattern_parsing(self, temp_dir):
        """Test that filename patterns are recognized (e.g., VID_YYYYMMDD_HHMMSS)"""
        video_path = os.path.join(temp_dir, "VID_20250618_072521.mp4")
        create_test_video(video_path)

        # Should use filename with provided timezone
        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video_path,
            "--timezone", "+0800"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        assert "@@timestamp_source=filename" in result.stdout
        assert "2025-06-18" in result.stderr or "2025:06:18" in result.stderr

    def test_missing_timezone_error(self, test_video_no_timezone):
        """--timezone is required even for a naive source with a usable DateTimeOriginal"""
        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            test_video_no_timezone
        ], capture_output=True, text=True)

        assert result.returncode == 1
        assert "--timezone is required" in result.stderr

    def test_missing_timezone_error_even_when_source_already_zoned(self, test_video):
        """--timezone is required for the step even when DateTimeOriginal already carries a zone"""
        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            test_video
        ], capture_output=True, text=True)

        assert result.returncode == 1
        assert "--timezone is required" in result.stderr

    def test_apply_without_timezone_writes_nothing_to_a_naive_file(self, test_video_no_timezone):
        """A batch run with no --timezone must leave naive files completely alone,
        rather than stamping them with whatever zone was last in play"""
        def time_tags():
            # -time:all also dumps FileAccessDate/FileInodeChangeDate, which the OS
            # updates on every read (including this dump's own read) regardless of
            # what the script writes — list the writable clock fields explicitly.
            dump = subprocess.run(
                ["exiftool", "-s"] + _CLOCK_FIELDS + [test_video_no_timezone],
                capture_output=True, text=True, check=True,
            )
            return dump.stdout

        before = time_tags()
        before_mtime = os.stat(test_video_no_timezone).st_mtime
        assert "+" not in before.split("DateTimeOriginal")[1].split("\n")[0]

        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            test_video_no_timezone, "--apply"
        ], capture_output=True, text=True)

        assert time_tags() == before
        assert os.stat(test_video_no_timezone).st_mtime == before_mtime
        assert result.returncode == 1
        assert "--timezone is required" in result.stderr

    def test_output_formatting(self, test_video):
        """Test that output follows data/presentation separation"""
        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            test_video, "--timezone", "+08:00"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        # Human-readable output on stderr
        assert "📅 Original" in result.stderr or "Original" in result.stderr
        assert "⏱️ Corrected" in result.stderr or "Corrected" in result.stderr
        assert "🌐 UTC" in result.stderr or "UTC" in result.stderr
        assert "📊 Change" in result.stderr or "Change" in result.stderr

    def test_quicktime_createdate_healing(self, test_video):
        """Test that corrupted QuickTime CreateDate is healed"""
        # Corrupt the QuickTime CreateDate
        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            "-QuickTime:CreateDate=2020:01:01 00:00:00",
            test_video
        ], capture_output=True, check=True)

        # Run fix
        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            test_video, "--timezone", "+08:00", "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        assert "QuickTime:CreateDate" in result.stderr

        # Verify QuickTime CreateDate is now correct (in UTC)
        exif_result = subprocess.run([
            "exiftool", "-s", "-QuickTime:MediaCreateDate", test_video
        ], capture_output=True, text=True, check=True)

        # Should be UTC time (2025-06-17 23:25:21 for +08:00 timezone)
        assert "2025:06:17 23:25:21" in exif_result.stdout


    def test_quicktime_track_atom_healed(self, test_video):
        """A correction reaches the per-track tkhd atom, not just the movie header,
        so a player reading TrackCreateDate sees the corrected time too."""
        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            "-QuickTime:TrackCreateDate=2020:01:01 00:00:00",
            test_video
        ], capture_output=True, check=True)

        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            test_video, "--timezone", "+08:00", "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0, result.stderr
        assert "QuickTime:TrackCreateDate" in result.stderr

        exif_result = subprocess.run([
            "exiftool", "-s", "-QuickTime:TrackCreateDate", test_video
        ], capture_output=True, text=True, check=True)

        assert "2025:06:17 23:25:21" in exif_result.stdout

    def test_stale_movie_header_is_corrected_when_tracks_are_already_right(self, temp_dir):
        """The Korea import case: DateTimeOriginal and both track atoms already carry
        the corrected instant while the mvhd movie header is 8 hours off. The run must
        report a change, heal the header to the same instant as the track atoms, and
        leave the correct DateTimeOriginal alone."""
        video = os.path.join(temp_dir, "stale_header.mp4")
        create_test_video(video, DateTimeOriginal="2025:08:15 15:07:42+09:00")
        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            "-QuickTime:CreateDate=2025:08:15 14:07:42",
            "-QuickTime:MediaCreateDate=2025:08:15 06:07:42",
            "-QuickTime:TrackCreateDate=2025:08:15 06:07:42",
            video
        ], capture_output=True, check=True)

        dry = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video, "--timezone", "+09:00", "--force-timezone"
        ], capture_output=True, text=True)
        assert dry.returncode == 0, dry.stderr
        assert "QuickTime:CreateDate" in dry.stderr
        assert "No change" not in dry.stderr

        applied = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video, "--timezone", "+09:00", "--force-timezone", "--apply"
        ], capture_output=True, text=True)
        assert applied.returncode == 0, applied.stderr

        after = subprocess.run([
            "exiftool", "-s",
            "-QuickTime:CreateDate", "-QuickTime:MediaCreateDate",
            "-QuickTime:TrackCreateDate", "-XMP-exif:DateTimeOriginal",
            video
        ], capture_output=True, text=True, check=True).stdout

        values = dict(
            (line.split(":", 1)[0].strip(), line.split(":", 1)[1].strip())
            for line in after.strip().splitlines()
        )
        assert values["CreateDate"] == "2025:08:15 06:07:42"
        assert values["MediaCreateDate"] == "2025:08:15 06:07:42"
        assert values["TrackCreateDate"] == "2025:08:15 06:07:42"
        assert values["DateTimeOriginal"] == "2025:08:15 15:07:42+09:00"


_CLOCK_FIELDS = [
    "-DateTimeOriginal", "-XMP-exif:DateTimeOriginal", "-Keys:CreationDate",
    "-QuickTime:CreateDate", "-QuickTime:MediaCreateDate",
    "-QuickTime:TrackCreateDate", "-XMP-xmpDM:LogComment", "-FileModifyDate",
]

_IDEMPOTENCE_FIELDS = [
    "-DateTimeOriginal", "-Keys:CreationDate",
    "-QuickTime:CreateDate", "-QuickTime:MediaCreateDate",
    "-QuickTime:TrackCreateDate",
]

# One case per source in the 6-tier ranking that --timezone can relabel. Each
# tuple is (filename, exif tags written to the pristine fixture, CLI args
# beyond the file path). --time-offset is excluded by design: it is a delta,
# so applying it twice is expected to shift the instant twice, not converge.
_RANKING_CASES = [
    pytest.param(
        "clip.mp4", {"DateTimeOriginal": "2025:06:18 07:25:21+08:00"},
        ["--timezone", "+09:00", "--force-timezone", "--apply"],
        id="datetimeoriginal-with-timezone",
    ),
    pytest.param(
        "clip.mp4", {"Keys:CreationDate": "2025:06:18 07:25:21+08:00"},
        ["--timezone", "+09:00", "--force-timezone", "--apply"],
        id="creationdate-with-timezone",
    ),
    pytest.param(
        "clip.mp4", {"Keys:CreationDate": "2025:06:18 07:25:21Z"},
        ["--timezone", "+08:00", "--apply"],
        id="creationdate-with-z-utc",
    ),
    pytest.param(
        "VID_20260104_033532_00_001.mp4", {"QuickTime:MediaCreateDate": "2026:01:03 18:35:32"},
        ["--timezone", "+13:00", "--apply"],
        id="mediacreatedate-instant",
    ),
    pytest.param(
        "VID_20250618_072521_00_001.mp4", {},
        ["--timezone", "+08:00", "--apply"],
        id="filename",
    ),
    pytest.param(
        "clip.mp4", {"DateTimeOriginal": "2025:06:18 07:25:21"},
        ["--timezone", "+08:00", "--apply"],
        id="datetimeoriginal-naive",
    ),
    pytest.param(
        "clip2.mp4", {"QuickTime:MediaCreateDate": "2025:06:18 07:25:21"},
        ["--timezone", "+08:00", "--apply"],
        id="mediacreatedate-no-crosscheck",
    ),
]


class TestIdempotenceAcrossRanking:
    """Reprocessing a corrected file must yield what processing a pristine copy
    yields, for each source in the ranking that a declared --timezone relabels.
    """

    @pytest.fixture
    def temp_dir(self):
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        shutil.rmtree(tmpdir)

    def _read_fields(self, path):
        result = subprocess.run(
            ["exiftool", "-s"] + _IDEMPOTENCE_FIELDS + [path],
            capture_output=True, text=True, check=True,
        )
        return result.stdout

    @pytest.mark.parametrize("filename, exif_tags, apply_args", _RANKING_CASES)
    def test_reprocessing_matches_pristine_copy(self, temp_dir, filename, exif_tags, apply_args):
        pristine = os.path.join(temp_dir, filename)
        create_test_video(pristine, **exif_tags)

        reprocessed = os.path.join(temp_dir, f"reprocessed_{filename}")
        processed_once = os.path.join(temp_dir, f"once_{filename}")
        shutil.copy2(pristine, reprocessed)
        shutil.copy2(pristine, processed_once)

        cmd = [sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py")]

        first = subprocess.run(cmd + [reprocessed] + apply_args, capture_output=True, text=True)
        assert first.returncode == 0, first.stderr

        second = subprocess.run(cmd + [reprocessed] + apply_args, capture_output=True, text=True)
        assert second.returncode == 0, second.stderr
        assert "No change" in second.stderr, second.stderr

        once = subprocess.run(cmd + [processed_once] + apply_args, capture_output=True, text=True)
        assert once.returncode == 0, once.stderr

        assert self._read_fields(reprocessed) == self._read_fields(processed_once)

    @pytest.mark.parametrize("filename, exif_tags, apply_args", _RANKING_CASES)
    def test_original_epoch_equals_corrected_epoch(self, temp_dir, filename, exif_tags, apply_args):
        """A --timezone relabel must preserve the instant: the epoch read off the
        source before correction must equal the epoch written after it, for every
        source in the ranking. A dry run is enough — the @@ lines are emitted either way."""
        video = os.path.join(temp_dir, filename)
        create_test_video(video, **exif_tags)

        dry_args = [arg for arg in apply_args if arg != "--apply"]
        cmd = [sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"), video] + dry_args

        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr

        at_lines = _parse_at_lines(result.stdout)
        original_epoch = float(at_lines["original_epoch"])
        corrected_epoch = float(at_lines["corrected_epoch"])
        assert original_epoch == corrected_epoch, (
            f"Actual: original_epoch={original_epoch}, corrected_epoch={corrected_epoch}, "
            f"Expected: equal (a declared --timezone relabels, it does not move the instant)"
        )

    def test_time_offset_shifts_corrected_epoch_only(self, temp_dir):
        """--time-offset is the only thing that moves the instant: on a proven
        MediaCreateDate instant, corrected_epoch must land exactly the offset
        away from original_epoch."""
        filename = "VID_20260104_033532_00_001.mp4"
        video = os.path.join(temp_dir, filename)
        create_test_video(video, **{"QuickTime:MediaCreateDate": "2026:01:03 18:35:32"})

        cmd = [
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video, "--timezone", "+13:00", "--time-offset", "-7200",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr

        at_lines = _parse_at_lines(result.stdout)
        original_epoch = float(at_lines["original_epoch"])
        corrected_epoch = float(at_lines["corrected_epoch"])
        assert corrected_epoch == original_epoch - 7200, (
            f"Actual: corrected_epoch={corrected_epoch}, original_epoch={original_epoch}, "
            f"Expected: corrected_epoch == original_epoch - 7200"
        )


class TestFixMediaTimestampIntegration:
    """Integration tests for fix-media-timestamp.py with various file types"""

    @pytest.fixture
    def temp_dir(self):
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        shutil.rmtree(tmpdir)

    def test_multiple_files_same_result(self, temp_dir):
        """Test that processing multiple similar files gives consistent results"""
        videos = []
        for i in range(3):
            video_path = os.path.join(temp_dir, f"test_{i}.mp4")
            create_test_video(video_path, DateTimeOriginal="2025:06:18 07:25:21+08:00")
            videos.append(video_path)

        # Process all files
        results = []
        for video in videos:
            result = subprocess.run([
                sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
                video, "--timezone", "+08:00", "--apply"
            ], capture_output=True, text=True)
            results.append(result)

        # All should succeed
        assert all(r.returncode == 0 for r in results)

        # All should have similar output (same corrections needed)
        for i in range(len(results) - 1):
            # Compare key parts of output (human-readable on stderr)
            assert "Keys:CreationDate" in results[i].stderr
            assert "Keys:CreationDate" in results[i + 1].stderr


class TestFixMediaTimestampMachineOutput:
    """Test @@ machine-readable output from fix-media-timestamp.py"""

    @pytest.fixture
    def temp_dir(self):
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        shutil.rmtree(tmpdir)

    def test_dry_run_emits_would_fix(self, temp_dir):
        """Dry run on file needing fixes emits @@timestamp_action=would_fix

        Actual: stdout contains @@timestamp_action=would_fix
        Expected: would_fix action for a file that needs timestamp corrections
        """
        video = os.path.join(temp_dir, "test.mp4")
        create_test_video(video, DateTimeOriginal="2025:06:18 07:25:21+08:00")

        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"), video, "--timezone", "+08:00"
        ], capture_output=True, text=True)

        at_lines = _parse_at_lines(result.stdout)
        assert at_lines.get("file") == "test.mp4", f"Actual: @@file={at_lines.get('file')}, Expected: test.mp4"
        assert at_lines.get("timestamp_action") == "would_fix", f"Actual: @@timestamp_action={at_lines.get('timestamp_action')}, Expected: would_fix"
        assert at_lines.get("timestamp_source") == "datetimeoriginal", f"Actual: @@timestamp_source={at_lines.get('timestamp_source')}, Expected: datetimeoriginal"
        assert at_lines.get("original_time") == "2025:06:18 07:25:21+08:00"
        assert at_lines.get("corrected_time") == "2025:06:18 07:25:21+08:00"
        assert at_lines.get("timezone") == "+08:00"

    def test_no_change_emits_no_change(self, temp_dir):
        """File already correct emits @@timestamp_action=no_change

        Actual: stdout contains @@timestamp_action=no_change after second run
        Expected: no_change for a file that was already fixed
        """
        video = os.path.join(temp_dir, "test.mp4")
        create_test_video(video, DateTimeOriginal="2025:06:18 07:25:21+08:00")

        # First apply
        subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"), video, "--timezone", "+08:00", "--apply"
        ], capture_output=True, text=True)

        # Second run - should be no_change
        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"), video, "--timezone", "+08:00", "--apply"
        ], capture_output=True, text=True)

        at_lines = _parse_at_lines(result.stdout)
        assert at_lines.get("timestamp_action") == "no_change", f"Actual: @@timestamp_action={at_lines.get('timestamp_action')}, Expected: no_change"

    def test_apply_emits_fixed(self, temp_dir):
        """Apply mode emits @@timestamp_action=fixed

        Actual: stdout contains @@timestamp_action=fixed
        Expected: fixed action when changes are applied
        """
        video = os.path.join(temp_dir, "test.mp4")
        create_test_video(video, DateTimeOriginal="2025:06:18 07:25:21+08:00")

        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"), video, "--timezone", "+08:00", "--apply"
        ], capture_output=True, text=True)

        at_lines = _parse_at_lines(result.stdout)
        assert at_lines.get("timestamp_action") == "fixed", f"Actual: @@timestamp_action={at_lines.get('timestamp_action')}, Expected: fixed"

    def test_filename_source_detected(self, temp_dir):
        """Filename-based timestamp source emits @@timestamp_source=filename

        Actual: stdout contains @@timestamp_source=filename
        Expected: filename source for VID_YYYYMMDD_HHMMSS pattern
        """
        video = os.path.join(temp_dir, "VID_20250618_072521.mp4")
        create_test_video(video)

        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"), video,
            "--timezone", "+0800"
        ], capture_output=True, text=True)

        at_lines = _parse_at_lines(result.stdout)
        assert at_lines.get("timestamp_source") == "filename", f"Actual: @@timestamp_source={at_lines.get('timestamp_source')}, Expected: filename"

    def test_camera_zone_offset_present_when_quicktime_wins(self, temp_dir):
        """@@camera_zone_offset is emitted when a declared --timezone lets the
        QuickTime date win the ranking — camera was on Japan time in New Zealand.

        Actual: stdout contains @@camera_zone_offset=+09:00 alongside the winning
        MediaCreateDate source.
        Expected: the camera's own zone offset surfaces independently of --timezone.
        """
        video = os.path.join(temp_dir, "VID_20260104_033532_00_001.mp4")
        create_test_video(video, **{"QuickTime:MediaCreateDate": "2026:01:03 18:35:32"})

        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"), video,
            "--timezone", "+13:00"
        ], capture_output=True, text=True)

        at_lines = _parse_at_lines(result.stdout)
        assert at_lines.get("timestamp_source") == "mediacreatedate"
        assert at_lines.get("camera_zone_offset") == "+09:00", f"Actual: @@camera_zone_offset={at_lines.get('camera_zone_offset')}, Expected: +09:00"

    def test_camera_zone_offset_present_when_a_different_source_wins(self, temp_dir):
        """@@camera_zone_offset is emitted even when neither the filename nor the
        QuickTime date wins the ranking — a zoned DateTimeOriginal outranks both, but
        emission does not depend on which source wins.

        Actual: stdout contains @@camera_zone_offset=+09:00 alongside the winning
        DateTimeOriginal source.
        Expected: the field is independent of ranking outcome.
        """
        video = os.path.join(temp_dir, "VID_20260104_033532_00_001.mp4")
        create_test_video(video, DateTimeOriginal="2025:06:18 07:25:21+08:00",
                           **{"QuickTime:MediaCreateDate": "2026:01:03 18:35:32"})

        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"), video,
            "--timezone", "+13:00"
        ], capture_output=True, text=True)

        at_lines = _parse_at_lines(result.stdout)
        assert at_lines.get("timestamp_source") == "datetimeoriginal", f"Actual: @@timestamp_source={at_lines.get('timestamp_source')}, Expected: datetimeoriginal"
        assert at_lines.get("camera_zone_offset") == "+09:00", f"Actual: @@camera_zone_offset={at_lines.get('camera_zone_offset')}, Expected: +09:00"

    def test_camera_zone_offset_absent_without_quicktime_date(self, temp_dir):
        """@@camera_zone_offset is absent when there's no QuickTime date to compare
        against the filename.

        Actual: @@camera_zone_offset key is missing from stdout.
        Expected: the field is only emitted when both sources coexist.
        """
        video = os.path.join(temp_dir, "VID_20250618_072521.mp4")
        create_test_video(video)

        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"), video,
            "--timezone", "+0800"
        ], capture_output=True, text=True)

        at_lines = _parse_at_lines(result.stdout)
        assert "camera_zone_offset" not in at_lines, f"Actual: @@camera_zone_offset={at_lines.get('camera_zone_offset')}, Expected: absent"

    def test_stdout_only_has_at_lines(self, temp_dir):
        """Stdout contains only @@key=value lines, no human-readable text

        Actual: every non-empty stdout line starts with @@
        Expected: clean machine-readable output on stdout
        """
        video = os.path.join(temp_dir, "test.mp4")
        create_test_video(video, DateTimeOriginal="2025:06:18 07:25:21+08:00")

        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"), video
        ], capture_output=True, text=True)

        for line in result.stdout.strip().split("\n"):
            if line.strip():
                assert line.startswith("@@"), f"Actual: stdout line '{line}' is not @@-prefixed, Expected: all stdout lines are @@key=value"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
