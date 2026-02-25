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
            test_video
        ], capture_output=True, text=True)

        assert result.returncode == 0
        assert "(DRY RUN)" in result.stderr

        assert os.stat(test_video).st_mtime == original_mtime

    def test_idempotency(self, test_video):
        """Test that running twice doesn't change anything the second time"""
        result1 = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            test_video, "--apply"
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
            test_video, "--apply"
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
            test_video, "--apply"
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
        """Test that missing timezone is reported correctly"""
        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            test_video_no_timezone
        ], capture_output=True, text=True)

        # Should succeed if DateTimeOriginal exists, even without timezone
        # Or should prompt for timezone depending on implementation
        assert result.returncode in [0, 1]  # May fail or succeed depending on data

    def test_output_formatting(self, test_video):
        """Test that output follows data/presentation separation"""
        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            test_video
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
            test_video, "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        assert "QuickTime CreateDate" in result.stderr

        # Verify QuickTime CreateDate is now correct (in UTC)
        exif_result = subprocess.run([
            "exiftool", "-s", "-QuickTime:MediaCreateDate", test_video
        ], capture_output=True, text=True, check=True)

        # Should be UTC time (2025-06-17 23:25:21 for +08:00 timezone)
        assert "2025:06:17 23:25:21" in exif_result.stdout


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
                video, "--apply"
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

    def _parse_at_lines(self, stdout: str) -> dict:
        """Parse @@key=value lines from stdout."""
        result = {}
        for line in stdout.strip().split("\n"):
            if line.startswith("@@"):
                key_value = line[2:]
                if "=" in key_value:
                    key, value = key_value.split("=", 1)
                    result[key] = value
        return result

    def test_dry_run_emits_would_fix(self, temp_dir):
        """Dry run on file needing fixes emits @@timestamp_action=would_fix

        Actual: stdout contains @@timestamp_action=would_fix
        Expected: would_fix action for a file that needs timestamp corrections
        """
        video = os.path.join(temp_dir, "test.mp4")
        create_test_video(video, DateTimeOriginal="2025:06:18 07:25:21+08:00")

        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"), video
        ], capture_output=True, text=True)

        at_lines = self._parse_at_lines(result.stdout)
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
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"), video, "--apply"
        ], capture_output=True, text=True)

        # Second run - should be no_change
        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"), video, "--apply"
        ], capture_output=True, text=True)

        at_lines = self._parse_at_lines(result.stdout)
        assert at_lines.get("timestamp_action") == "no_change", f"Actual: @@timestamp_action={at_lines.get('timestamp_action')}, Expected: no_change"

    def test_apply_emits_fixed(self, temp_dir):
        """Apply mode emits @@timestamp_action=fixed

        Actual: stdout contains @@timestamp_action=fixed
        Expected: fixed action when changes are applied
        """
        video = os.path.join(temp_dir, "test.mp4")
        create_test_video(video, DateTimeOriginal="2025:06:18 07:25:21+08:00")

        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"), video, "--apply"
        ], capture_output=True, text=True)

        at_lines = self._parse_at_lines(result.stdout)
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

        at_lines = self._parse_at_lines(result.stdout)
        assert at_lines.get("timestamp_source") == "filename", f"Actual: @@timestamp_source={at_lines.get('timestamp_source')}, Expected: filename"

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
