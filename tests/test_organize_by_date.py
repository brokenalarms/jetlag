#!/usr/bin/env python3
"""
Tests for organize-by-date.sh
Validates file organization, template substitution, and idempotency
"""

import os
import subprocess
import tempfile
import shutil
from pathlib import Path
import pytest


SCRIPT_DIR = Path(__file__).parent.parent


class TestOrganizeByDate:
    """Test suite for organize-by-date.sh"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files"""
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        shutil.rmtree(tmpdir)

    @pytest.fixture
    def test_video_with_date(self, temp_dir):
        """Create test video with DateTimeOriginal"""
        video_path = os.path.join(temp_dir, "source", "test_video.mp4")
        os.makedirs(os.path.dirname(video_path), exist_ok=True)

        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            video_path
        ], capture_output=True, check=True)

        # Set DateTimeOriginal
        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            "-DateTimeOriginal=2025:06:18 07:25:21+08:00",
            video_path
        ], capture_output=True, check=True)

        return video_path

    def test_dry_run_no_move(self, test_video_with_date, temp_dir):
        """Test that dry run doesn't move files

        Actual: File stays in source, target empty
        Expected: Same (dry run = no changes)
        """
        target_dir = os.path.join(temp_dir, "target")
        os.makedirs(target_dir, exist_ok=True)

        # Record before state
        source_exists_before = os.path.exists(test_video_with_date)
        target_path = os.path.join(target_dir, "2025-06-18", "test_video.mp4")
        target_exists_before = os.path.exists(target_path)

        result = subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            test_video_with_date,
            "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--label", "Test"
        ], capture_output=True, text=True)

        # Record after state
        source_exists_after = os.path.exists(test_video_with_date)
        target_exists_after = os.path.exists(target_path)

        # Verify behavior: dry run should not move file
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert source_exists_before == True, "Source should exist before"
        assert target_exists_before == False, "Target should not exist before"
        assert source_exists_after == True, f"Actual: source missing after dry run, Expected: source still exists"
        assert target_exists_after == False, f"Actual: target created during dry run, Expected: target empty"

    def test_apply_mode_moves_file(self, test_video_with_date, temp_dir):
        """Test that apply mode moves file to correct location

        Actual: File moved to target, source empty
        Expected: File organized by date in target directory
        """
        target_dir = os.path.join(temp_dir, "target")
        os.makedirs(target_dir, exist_ok=True)

        # Record before state
        source_exists_before = os.path.exists(test_video_with_date)
        target_path = os.path.join(target_dir, "2025-06-18", "test_video.mp4")
        target_exists_before = os.path.exists(target_path)

        result = subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            test_video_with_date,
            "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--label", "Test",
            "--apply"
        ], capture_output=True, text=True)

        # Record after state
        source_exists_after = os.path.exists(test_video_with_date)
        target_exists_after = os.path.exists(target_path)

        # Verify behavior: file should be moved
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert source_exists_before == True, "Source should exist before"
        assert target_exists_before == False, "Target should not exist before"
        assert source_exists_after == False, f"Actual: source still exists after apply, Expected: source moved away"
        assert target_exists_after == True, f"Actual: target missing after apply, Expected: file at {target_path}"

    def test_template_substitution(self, test_video_with_date, temp_dir):
        """Test that template variables are substituted correctly

        Actual: File organized with template pattern
        Expected: File at 2025/Taiwan/2025-06-18/test_video.mp4
        """
        target_dir = os.path.join(temp_dir, "target")
        os.makedirs(target_dir, exist_ok=True)

        # Record before state
        source_exists_before = os.path.exists(test_video_with_date)
        expected_path = os.path.join(target_dir, "2025", "Taiwan", "2025-06-18", "test_video.mp4")
        target_exists_before = os.path.exists(expected_path)

        result = subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            test_video_with_date,
            "--target", target_dir,
            "--template", "{{YYYY}}/{{label}}/{{YYYY}}-{{MM}}-{{DD}}",
            "--label", "Taiwan",
            "--apply"
        ], capture_output=True, text=True)

        # Record after state
        source_exists_after = os.path.exists(test_video_with_date)
        target_exists_after = os.path.exists(expected_path)

        # Verify behavior: file should be organized with template pattern
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert source_exists_before == True, "Source should exist before"
        assert target_exists_before == False, "Target should not exist before"
        assert source_exists_after == False, f"Actual: source still exists, Expected: source moved"
        assert target_exists_after == True, f"Actual: file not at expected location, Expected: {expected_path}"

    def test_idempotency_already_organized(self, test_video_with_date, temp_dir):
        """Test that already-organized files are detected

        Actual: File stays in place after second run
        Expected: Idempotent behavior, file not moved again
        """
        target_dir = os.path.join(temp_dir, "target")
        os.makedirs(target_dir, exist_ok=True)

        # First run - organize file
        subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            test_video_with_date,
            "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--label", "Test",
            "--apply"
        ], capture_output=True, check=True)

        moved_path = os.path.join(target_dir, "2025-06-18", "test_video.mp4")
        assert os.path.exists(moved_path), "First run should organize file"

        # Get inode before second run
        stat_before = os.stat(moved_path)
        inode_before = stat_before.st_ino
        mtime_before = stat_before.st_mtime

        # Second run on already-organized file
        result = subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            moved_path,
            "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--label", "Test",
            "--apply"
        ], capture_output=True, text=True)

        # Get inode after second run
        stat_after = os.stat(moved_path)
        inode_after = stat_after.st_ino
        mtime_after = stat_after.st_mtime

        # Verify idempotent behavior: file should not be moved/modified
        assert result.returncode == 0, f"Script should succeed: {result.stderr}"
        assert os.path.exists(moved_path), "File should still exist at original location"
        assert inode_before == inode_after, f"Actual: file was moved (inode changed), Expected: file stays in place (same inode)"
        assert abs(mtime_after - mtime_before) < 2, f"Actual: file was modified, Expected: file unchanged"

    def test_label_required(self, test_video_with_date, temp_dir):
        """Test that --label is required when template uses {{label}}

        Actual: Script should fail
        Expected: Error message about missing label
        """
        target_dir = os.path.join(temp_dir, "target")

        # Should fail without --label when template uses {{label}}
        result = subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            test_video_with_date,
            "--target", target_dir,
            "--template", "{{label}}/{{YYYY}}-{{MM}}-{{DD}}"
        ], capture_output=True, text=True)

        # Verify error handling
        assert result.returncode != 0, f"Actual: script succeeded, Expected: script should fail when {{{{label}}}} in template but no --label provided. stderr: {result.stderr}"
        assert "label" in result.stderr.lower(), f"Actual: no 'label' in error message, Expected: error mentions 'label'. stderr: {result.stderr}"

    def test_creates_directories(self, test_video_with_date, temp_dir):
        """Test that directory structure is created"""
        target_dir = os.path.join(temp_dir, "target")
        # Don't create target_dir - script should create it

        result = subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            test_video_with_date,
            "--target", target_dir,
            "--template", "{{YYYY}}/{{MM}}/{{DD}}",
            "--label", "Test",
            "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0

        # Directory structure should be created
        expected_path = os.path.join(target_dir, "2025", "06", "18", "test_video.mp4")
        assert os.path.exists(expected_path)

    def test_multiple_files_same_date(self, temp_dir):
        """Test organizing multiple files with same date"""
        source_dir = os.path.join(temp_dir, "source")
        target_dir = os.path.join(temp_dir, "target")
        os.makedirs(source_dir, exist_ok=True)
        os.makedirs(target_dir, exist_ok=True)

        # Create multiple videos
        videos = []
        for i in range(3):
            video_path = os.path.join(source_dir, f"test_{i}.mp4")
            subprocess.run([
                "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
                "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
                video_path
            ], capture_output=True, check=True)

            subprocess.run([
                "exiftool", "-P", "-overwrite_original",
                "-DateTimeOriginal=2025:06:18 07:25:21+08:00",
                video_path
            ], capture_output=True, check=True)

            videos.append(video_path)

        # Organize all videos
        for video in videos:
            subprocess.run([
                "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
                video,
                "--target", target_dir,
                "--template", "{{YYYY}}-{{MM}}-{{DD}}",
                "--label", "Test",
                "--apply"
            ], capture_output=True, check=True)

        # All should be in same directory
        date_dir = os.path.join(target_dir, "2025-06-18")
        assert len(os.listdir(date_dir)) == 3

    def test_output_format(self, test_video_with_date, temp_dir):
        """Test output formatting"""
        target_dir = os.path.join(temp_dir, "target")

        result = subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            test_video_with_date,
            "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--label", "Test"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        # Should show filename
        assert "test_video.mp4" in result.stdout
        # Should show target path or indication of where it will go
        assert "2025-06-18" in result.stdout or "2025/06/18" in result.stdout


class TestOrganizeByDateEdgeCases:
    """Edge case tests for organize-by-date.sh"""

    @pytest.fixture
    def temp_dir(self):
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        shutil.rmtree(tmpdir)

    def test_file_without_metadata(self, temp_dir):
        """Test handling file without DateTimeOriginal"""
        source_dir = os.path.join(temp_dir, "source")
        target_dir = os.path.join(temp_dir, "target")
        os.makedirs(source_dir, exist_ok=True)

        video_path = os.path.join(source_dir, "no_metadata.mp4")
        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            video_path
        ], capture_output=True, check=True)

        # Should fail or use fallback (depending on implementation)
        result = subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            video_path,
            "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--label", "Test"
        ], capture_output=True, text=True)

        # May succeed with file birthtime or fail - both valid
        assert result.returncode in [0, 1]

    def test_filename_with_spaces(self, temp_dir):
        """Test handling filenames with spaces"""
        source_dir = os.path.join(temp_dir, "source")
        target_dir = os.path.join(temp_dir, "target")
        os.makedirs(source_dir, exist_ok=True)
        os.makedirs(target_dir, exist_ok=True)

        video_path = os.path.join(source_dir, "test video with spaces.mp4")
        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            video_path
        ], capture_output=True, check=True)

        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            "-DateTimeOriginal=2025:06:18 07:25:21+08:00",
            video_path
        ], capture_output=True, check=True)

        result = subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            video_path,
            "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--label", "Test",
            "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        expected_path = os.path.join(target_dir, "2025-06-18", "test video with spaces.mp4")
        assert os.path.exists(expected_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
