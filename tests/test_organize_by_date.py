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
            "--template", "{{YYYY}}-{{MM}}-{{DD}}"
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
            "--template", "{{YYYY}}/Taiwan/{{YYYY}}-{{MM}}-{{DD}}",
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

    def test_creates_directories(self, test_video_with_date, temp_dir):
        """Test that directory structure is created"""
        target_dir = os.path.join(temp_dir, "target")
        # Don't create target_dir - script should create it

        result = subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            test_video_with_date,
            "--target", target_dir,
            "--template", "{{YYYY}}/{{MM}}/{{DD}}",
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
            "--template", "{{YYYY}}-{{MM}}-{{DD}}"
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
            "--template", "{{YYYY}}-{{MM}}-{{DD}}"
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
            "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        expected_path = os.path.join(target_dir, "2025-06-18", "test video with spaces.mp4")
        assert os.path.exists(expected_path)


class TestCopyMode:
    """Tests for --copy mode (used by import-media)."""

    @pytest.fixture
    def temp_dir(self):
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        shutil.rmtree(tmpdir)

    def _create_video(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p", path
        ], capture_output=True, check=True)
        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            "-DateTimeOriginal=2025:06:18 07:25:21+08:00", path
        ], capture_output=True, check=True)

    def test_copy_mode_preserves_source(self, temp_dir):
        """--copy leaves source file in place."""
        source = os.path.join(temp_dir, "source", "test.mp4")
        target_dir = os.path.join(temp_dir, "target")
        self._create_video(source)

        result = subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            source, "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--copy", "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        assert os.path.exists(source), "Source must remain after copy"
        assert os.path.exists(os.path.join(target_dir, "2025-06-18", "test.mp4"))

    def test_copy_mode_action_output(self, temp_dir):
        """--copy emits @@action=copied on stdout."""
        source = os.path.join(temp_dir, "source", "test.mp4")
        target_dir = os.path.join(temp_dir, "target")
        self._create_video(source)

        result = subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            source, "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--copy", "--apply"
        ], capture_output=True, text=True)

        assert "@@action=copied" in result.stdout


class TestMachineOutput:
    """Tests for @@key=value stdout output and stderr/stdout split."""

    @pytest.fixture
    def temp_dir(self):
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        shutil.rmtree(tmpdir)

    def _create_video(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p", path
        ], capture_output=True, check=True)
        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            "-DateTimeOriginal=2025:06:18 07:25:21+08:00", path
        ], capture_output=True, check=True)

    def test_move_action_output(self, temp_dir):
        """Move mode emits @@action=moved on stdout."""
        source = os.path.join(temp_dir, "source", "test.mp4")
        target_dir = os.path.join(temp_dir, "target")
        self._create_video(source)

        result = subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            source, "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--apply"
        ], capture_output=True, text=True)

        assert "@@action=moved" in result.stdout

    def test_dry_run_would_move_action(self, temp_dir):
        """Dry run emits @@action=would_move."""
        source = os.path.join(temp_dir, "source", "test.mp4")
        target_dir = os.path.join(temp_dir, "target")
        self._create_video(source)

        result = subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            source, "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}"
        ], capture_output=True, text=True)

        assert "@@action=would_move" in result.stdout

    def test_dry_run_would_copy_action(self, temp_dir):
        """Dry run with --copy emits @@action=would_copy."""
        source = os.path.join(temp_dir, "source", "test.mp4")
        target_dir = os.path.join(temp_dir, "target")
        self._create_video(source)

        result = subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            source, "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--copy"
        ], capture_output=True, text=True)

        assert "@@action=would_copy" in result.stdout

    def test_dest_output_is_absolute(self, temp_dir):
        """@@dest= value is an absolute path."""
        source = os.path.join(temp_dir, "source", "test.mp4")
        target_dir = os.path.join(temp_dir, "target")
        self._create_video(source)

        result = subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            source, "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--apply"
        ], capture_output=True, text=True)

        for line in result.stdout.split('\n'):
            if line.startswith('@@dest='):
                dest = line.split('=', 1)[1]
                assert os.path.isabs(dest), f"@@dest should be absolute, got: {dest}"

    def test_stdout_only_machine_readable(self, temp_dir):
        """stdout contains only @@key=value lines, human messages go to stderr."""
        source = os.path.join(temp_dir, "source", "test.mp4")
        target_dir = os.path.join(temp_dir, "target")
        self._create_video(source)

        result = subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            source, "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--apply"
        ], capture_output=True, text=True)

        for line in result.stdout.strip().split('\n'):
            if line.strip():
                assert line.startswith('@@'), f"Non-@@ line on stdout: {line!r}"

        assert result.stderr.strip(), "Human-readable output should be on stderr"

    def test_skipped_action_for_already_organized(self, temp_dir):
        """Already-organized file emits @@action=skipped."""
        source = os.path.join(temp_dir, "source", "test.mp4")
        target_dir = os.path.join(temp_dir, "target")
        self._create_video(source)

        # First run: move file
        subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            source, "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--apply"
        ], capture_output=True, check=True)

        moved_path = os.path.join(target_dir, "2025-06-18", "test.mp4")

        # Second run: same file already in place
        result = subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            moved_path, "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--apply"
        ], capture_output=True, text=True)

        assert "@@action=skipped" in result.stdout


class TestOverwriteMode:
    """Tests for --overwrite and same-size auto-skip."""

    @pytest.fixture
    def temp_dir(self):
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        shutil.rmtree(tmpdir)

    def _create_video(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p", path
        ], capture_output=True, check=True)
        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            "-DateTimeOriginal=2025:06:18 07:25:21+08:00", path
        ], capture_output=True, check=True)

    def test_same_size_auto_skips(self, temp_dir):
        """Existing file with same size is auto-skipped."""
        source = os.path.join(temp_dir, "source", "test.mp4")
        target_dir = os.path.join(temp_dir, "target")
        self._create_video(source)

        # First copy
        subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            source, "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--copy", "--apply"
        ], capture_output=True, check=True)

        # Second copy of same file (same size)
        result = subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            source, "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--copy", "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        assert "@@action=skipped" in result.stdout

    def test_overwrite_replaces_existing(self, temp_dir):
        """--overwrite replaces existing file instead of skipping."""
        source = os.path.join(temp_dir, "source", "test.mp4")
        target_dir = os.path.join(temp_dir, "target")
        self._create_video(source)

        # First copy
        subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            source, "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--copy", "--apply"
        ], capture_output=True, check=True)

        dest_path = os.path.join(target_dir, "2025-06-18", "test.mp4")
        assert os.path.exists(dest_path)

        # Without --overwrite, same-size file is skipped
        skip_result = subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            source, "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--copy", "--apply"
        ], capture_output=True, text=True)
        assert "@@action=skipped" in skip_result.stdout

        # With --overwrite, file is overwritten
        result = subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            source, "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--copy", "--overwrite", "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        assert "@@action=overwrote" in result.stdout


class TestDirectoryCleanupAfterMove:
    """Tests for empty directory cleanup in organize-by-date.sh after move."""

    @pytest.fixture
    def temp_dir(self):
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        shutil.rmtree(tmpdir)

    def _create_video(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p", path
        ], capture_output=True, check=True)
        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            "-DateTimeOriginal=2025:06:18 07:25:21+08:00", path
        ], capture_output=True, check=True)

    def test_empty_source_dir_removed_after_move(self, temp_dir):
        """Source directory is cleaned up after last file is moved out."""
        subdir = os.path.join(temp_dir, "source", "subdir")
        source = os.path.join(subdir, "test.mp4")
        target_dir = os.path.join(temp_dir, "target")
        self._create_video(source)

        subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            source, "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--apply"
        ], capture_output=True, check=True)

        assert not os.path.exists(subdir), "Empty source subdir should be removed"

    def test_ds_store_only_dir_removed(self, temp_dir):
        """Directory with only .DS_Store is cleaned up after move."""
        subdir = os.path.join(temp_dir, "source", "subdir")
        source = os.path.join(subdir, "test.mp4")
        target_dir = os.path.join(temp_dir, "target")
        self._create_video(source)
        Path(os.path.join(subdir, ".DS_Store")).write_bytes(b"fake")

        subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            source, "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--apply"
        ], capture_output=True, check=True)

        assert not os.path.exists(subdir), "Dir with only .DS_Store should be removed"

    def test_nonempty_dir_preserved(self, temp_dir):
        """Directory with other files is not removed after move."""
        subdir = os.path.join(temp_dir, "source", "subdir")
        source = os.path.join(subdir, "test.mp4")
        target_dir = os.path.join(temp_dir, "target")
        self._create_video(source)
        Path(os.path.join(subdir, "other.txt")).write_bytes(b"keep")

        subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            source, "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--apply"
        ], capture_output=True, check=True)

        assert os.path.exists(subdir), "Dir with other files should remain"
        assert os.path.exists(os.path.join(subdir, "other.txt"))

    def test_copy_mode_no_cleanup(self, temp_dir):
        """Copy mode should not remove source directories."""
        subdir = os.path.join(temp_dir, "source", "subdir")
        source = os.path.join(subdir, "test.mp4")
        target_dir = os.path.join(temp_dir, "target")
        self._create_video(source)

        subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            source, "--target", target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--copy", "--apply"
        ], capture_output=True, check=True)

        assert os.path.exists(subdir), "Copy mode should not clean up source"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
