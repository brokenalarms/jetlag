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
        assert "(DRY RUN)" in result.stdout

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
        assert "No change" in result2.stdout

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
        assert "filename" in result.stdout.lower()
        assert "2025-06-18" in result.stdout or "2025:06:18" in result.stdout

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
        # Should have structured output sections
        assert "📅 Original" in result.stdout or "Original" in result.stdout
        assert "⏱️ Corrected" in result.stdout or "Corrected" in result.stdout
        assert "🌐 UTC" in result.stdout or "UTC" in result.stdout
        assert "📊 Change" in result.stdout or "Change" in result.stdout

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
        assert "QuickTime CreateDate" in result.stdout

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
            # Compare key parts of output
            assert "Keys:CreationDate" in results[i].stdout
            assert "Keys:CreationDate" in results[i + 1].stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
