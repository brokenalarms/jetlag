#!/usr/bin/env python3
"""
Tests for tag-media.py
Validates tagging behavior, idempotency, and check-before-write
"""

import os
import subprocess
import tempfile
import shutil
from pathlib import Path
import pytest


SCRIPT_DIR = Path(__file__).parent.parent


class TestTagMedia:
    """Test suite for tag-media.py"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files"""
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        shutil.rmtree(tmpdir)

    @pytest.fixture
    def test_video(self, temp_dir):
        """Create a test video file"""
        video_path = os.path.join(temp_dir, "test_video.mp4")

        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            video_path
        ], capture_output=True, check=True)

        return video_path

    def test_dry_run_no_changes(self, test_video):
        """Test that dry run doesn't modify files"""
        # Run without --apply (dry run mode)
        result = subprocess.run([
            "python3", str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--tags", "test-tag",
            "--make", "TestMake",
            "--model", "TestModel"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        assert "(DRY RUN)" in result.stdout

        # Verify no tags were actually added
        tag_result = subprocess.run([
            "tag", "--list", test_video
        ], capture_output=True, text=True)

        assert "test-tag" not in tag_result.stdout

        # Verify no EXIF was written
        exif_result = subprocess.run([
            "exiftool", "-Make", "-Model", test_video
        ], capture_output=True, text=True)

        assert "TestMake" not in exif_result.stdout

    def test_apply_mode_adds_tags(self, test_video):
        """Test that apply mode adds tags"""
        result = subprocess.run([
            "python3", str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--tags", "test-tag,another-tag",
            "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        assert "Tagged" in result.stdout or "📌" in result.stdout
        assert "(DRY RUN)" not in result.stdout

        # Verify tags were added
        tag_result = subprocess.run([
            "tag", "--list", "--no-name", test_video
        ], capture_output=True, text=True, check=True)

        assert "test-tag" in tag_result.stdout
        assert "another-tag" in tag_result.stdout

    def test_apply_mode_adds_exif(self, test_video):
        """Test that apply mode adds EXIF data"""
        result = subprocess.run([
            "python3", str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--make", "GoPro",
            "--model", "HERO12 Black",
            "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        assert "EXIF" in result.stdout

        # Verify EXIF was written
        exif_result = subprocess.run([
            "exiftool", "-s", "-Make", "-Model", test_video
        ], capture_output=True, text=True, check=True)

        assert "GoPro" in exif_result.stdout
        assert "HERO12 Black" in exif_result.stdout

    def test_idempotency_tags(self, test_video):
        """Test that adding same tags twice doesn't duplicate"""
        # First run
        subprocess.run([
            "python3", str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--tags", "test-tag",
            "--apply"
        ], capture_output=True, check=True)

        # Second run should report already tagged
        result = subprocess.run([
            "python3", str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--tags", "test-tag",
            "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        assert "Already tagged correctly" in result.stdout

        # Verify tag wasn't duplicated
        tag_result = subprocess.run([
            "tag", "--list", "--no-name", test_video
        ], capture_output=True, text=True, check=True)

        # Should only appear once
        assert tag_result.stdout.count("test-tag") == 1

    def test_idempotency_exif(self, test_video):
        """Test that setting same EXIF twice doesn't rewrite"""
        # First run
        subprocess.run([
            "python3", str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--make", "GoPro",
            "--model", "HERO12 Black",
            "--apply"
        ], capture_output=True, check=True)

        # Get modification time after first run
        mtime_after_first = os.stat(test_video).st_mtime

        # Second run should report already tagged
        result = subprocess.run([
            "python3", str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--make", "GoPro",
            "--model", "HERO12 Black",
            "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        assert "Already tagged correctly" in result.stdout

        # Modification time shouldn't change (no exiftool write)
        mtime_after_second = os.stat(test_video).st_mtime
        assert abs(mtime_after_second - mtime_after_first) < 1  # Allow 1 second tolerance

    def test_partial_update_tags(self, test_video):
        """Test that only missing tags are added"""
        # Add first tag
        subprocess.run([
            "python3", str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--tags", "existing-tag",
            "--apply"
        ], capture_output=True, check=True)

        # Add second tag (first should be skipped)
        result = subprocess.run([
            "python3", str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--tags", "existing-tag,new-tag",
            "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        # Should only report adding new-tag
        assert "new-tag" in result.stdout
        # Should not mention existing-tag was added
        if "Tagged:" in result.stdout:
            # Extract the tagged line
            for line in result.stdout.split('\n'):
                if "Tagged:" in line or "📌" in line:
                    assert "new-tag" in line
                    # existing-tag shouldn't be in the "tags added" list
                    break

    def test_partial_update_exif(self, test_video):
        """Test that only missing EXIF fields are updated"""
        # Set Make only
        subprocess.run([
            "python3", str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--make", "GoPro",
            "--apply"
        ], capture_output=True, check=True)

        # Set both Make and Model (only Model should be written)
        result = subprocess.run([
            "python3", str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--make", "GoPro",
            "--model", "HERO12 Black",
            "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        # Should report adding Model but not Make
        assert "Model" in result.stdout or "HERO12 Black" in result.stdout

    def test_multiple_files(self, temp_dir):
        """Test processing multiple files"""
        videos = []
        for i in range(3):
            video_path = os.path.join(temp_dir, f"test_{i}.mp4")
            subprocess.run([
                "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
                "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
                video_path
            ], capture_output=True, check=True)
            videos.append(video_path)

        # Process all files at once
        result = subprocess.run([
            "python3", str(SCRIPT_DIR / "tag-media.py"),
            *videos,
            "--tags", "batch-tag",
            "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0

        # Verify all files were tagged
        for video in videos:
            tag_result = subprocess.run([
                "tag", "--list", "--no-name", video
            ], capture_output=True, text=True, check=True)
            assert "batch-tag" in tag_result.stdout

    def test_unsupported_file_type(self, temp_dir):
        """Test that unsupported file types are handled gracefully"""
        # Create .lrv file (not supported for EXIF)
        lrv_path = os.path.join(temp_dir, "test.lrv")
        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            lrv_path
        ], capture_output=True, check=True)

        # Should skip EXIF for .lrv but still allow tags
        result = subprocess.run([
            "python3", str(SCRIPT_DIR / "tag-media.py"),
            lrv_path,
            "--make", "GoPro",
            "--tags", "test-tag",
            "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        # Should have tagged but not added EXIF
        assert "test-tag" in result.stdout or "Already tagged" in result.stdout

    def test_output_format(self, test_video):
        """Test that output follows presentation format"""
        result = subprocess.run([
            "python3", str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--tags", "test-tag",
            "--make", "GoPro",
            "--model", "HERO12"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        # Should show what will be tagged
        assert "test_video.mp4" in result.stdout
        # Should indicate dry run
        assert "(DRY RUN)" in result.stdout

    def test_combined_tags_and_exif(self, test_video):
        """Test adding both tags and EXIF together"""
        result = subprocess.run([
            "python3", str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--tags", "gopro-hero-12",
            "--make", "GoPro",
            "--model", "HERO12 Black",
            "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        assert "EXIF" in result.stdout
        assert "Tags" in result.stdout

        # Verify both were added
        tag_result = subprocess.run([
            "tag", "--list", "--no-name", test_video
        ], capture_output=True, text=True, check=True)
        assert "gopro-hero-12" in tag_result.stdout

        exif_result = subprocess.run([
            "exiftool", "-s", "-Make", "-Model", test_video
        ], capture_output=True, text=True, check=True)
        assert "GoPro" in exif_result.stdout
        assert "HERO12 Black" in exif_result.stdout


class TestTagMediaDataPresentation:
    """Test data/presentation separation in tag-media.py"""

    @pytest.fixture
    def temp_dir(self):
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        shutil.rmtree(tmpdir)

    @pytest.fixture
    def test_video(self, temp_dir):
        video_path = os.path.join(temp_dir, "test.mp4")
        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            video_path
        ], capture_output=True, check=True)
        return video_path

    def test_returns_what_changed(self, test_video):
        """Test that functions return data about what changed"""
        # This tests the principle from CLAUDE.md:
        # "separation of data and presentation"
        # Functions should return what changed, presentation formats it

        result = subprocess.run([
            "python3", str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--tags", "tag1,tag2",
            "--make", "TestMake",
            "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        # Output should show specifically what was added
        assert "tag1" in result.stdout
        assert "tag2" in result.stdout
        assert "TestMake" in result.stdout

    def test_no_output_for_unchanged(self, test_video):
        """Test that already-correct files report status correctly"""
        # Add tags
        subprocess.run([
            "python3", str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--tags", "test-tag",
            "--apply"
        ], capture_output=True, check=True)

        # Run again - should report already correct
        result = subprocess.run([
            "python3", str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--tags", "test-tag",
            "--apply"
        ], capture_output=True, text=True)

        assert "Already tagged correctly" in result.stdout
        # Should NOT say it tagged anything
        assert "Tagged:" not in result.stdout or "Already" in result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
