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
        """Test that dry run doesn't move files"""
        target_dir = os.path.join(temp_dir, "target")
        os.makedirs(target_dir, exist_ok=True)

        result = subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            test_video_with_date,
            "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--label", "Test"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        assert "(DRY RUN)" in result.stdout

        # File should still be in original location
        assert os.path.exists(test_video_with_date)

        # Target directory should not have the file
        assert not os.path.exists(os.path.join(target_dir, "2025-06-18", "test_video.mp4"))

    def test_apply_mode_moves_file(self, test_video_with_date, temp_dir):
        """Test that apply mode moves file to correct location"""
        target_dir = os.path.join(temp_dir, "target")
        os.makedirs(target_dir, exist_ok=True)

        result = subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            test_video_with_date,
            "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--label", "Test",
            "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        assert "(DRY RUN)" not in result.stdout

        # File should be moved to target
        expected_path = os.path.join(target_dir, "2025-06-18", "test_video.mp4")
        assert os.path.exists(expected_path)

        # Original should be gone
        assert not os.path.exists(test_video_with_date)

    def test_template_substitution(self, test_video_with_date, temp_dir):
        """Test that template variables are substituted correctly"""
        target_dir = os.path.join(temp_dir, "target")
        os.makedirs(target_dir, exist_ok=True)

        result = subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            test_video_with_date,
            "--target", target_dir,
            "--template", "{{YYYY}}/{{LABEL}}/{{YYYY}}-{{MM}}-{{DD}}",
            "--label", "Taiwan",
            "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0

        # File should be in 2025/Taiwan/2025-06-18/
        expected_path = os.path.join(target_dir, "2025", "Taiwan", "2025-06-18", "test_video.mp4")
        assert os.path.exists(expected_path)

    def test_idempotency_already_organized(self, test_video_with_date, temp_dir):
        """Test that already-organized files are detected"""
        target_dir = os.path.join(temp_dir, "target")
        os.makedirs(target_dir, exist_ok=True)

        # First run
        subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            test_video_with_date,
            "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--label", "Test",
            "--apply"
        ], capture_output=True, check=True)

        moved_path = os.path.join(target_dir, "2025-06-18", "test_video.mp4")
        assert os.path.exists(moved_path)

        # Second run on moved file should report already organized
        result = subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            moved_path,
            "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--label", "Test",
            "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        assert "Already organized" in result.stdout

    def test_label_required(self, test_video_with_date, temp_dir):
        """Test that --label is required when template uses {{LABEL}}"""
        target_dir = os.path.join(temp_dir, "target")

        # Should fail without --label when template uses {{LABEL}}
        result = subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            test_video_with_date,
            "--target", target_dir,
            "--template", "{{LABEL}}/{{YYYY}}-{{MM}}-{{DD}}"
        ], capture_output=True, text=True)

        assert result.returncode != 0
        assert "label" in result.stderr.lower() or "LABEL" in result.stderr

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
