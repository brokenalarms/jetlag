#!/usr/bin/env python3
"""
Tests for tag-media.py
Validates tagging behavior, idempotency, and check-before-write
"""

import os
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path
import pytest

from conftest import create_test_video


SCRIPT_DIR = Path(__file__).parent.parent

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="requires macOS — Finder tags don't exist on Linux")


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
        create_test_video(video_path)
        return video_path

    def test_dry_run_no_changes(self, test_video):
        """Test that dry run doesn't modify files

        Actual: File unchanged after dry run
        Expected: No tags or EXIF added in dry run mode
        """
        # Record before state
        tag_result_before = subprocess.run([
            "tag", "--list", test_video
        ], capture_output=True, text=True)
        has_tag_before = "test-tag" in tag_result_before.stdout

        exif_result_before = subprocess.run([
            "exiftool", "-Make", "-Model", test_video
        ], capture_output=True, text=True)
        has_make_before = "TestMake" in exif_result_before.stdout

        # Run without --apply (dry run mode)
        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--tags", "test-tag",
            "--make", "TestMake",
            "--model", "TestModel"
        ], capture_output=True, text=True)

        # Record after state
        tag_result_after = subprocess.run([
            "tag", "--list", test_video
        ], capture_output=True, text=True)
        has_tag_after = "test-tag" in tag_result_after.stdout

        exif_result_after = subprocess.run([
            "exiftool", "-Make", "-Model", test_video
        ], capture_output=True, text=True)
        has_make_after = "TestMake" in exif_result_after.stdout

        # Verify behavior: dry run should not modify file
        assert result.returncode == 0, f"Script should succeed: {result.stderr}"
        assert has_tag_before == False, "Tag should not exist before"
        assert has_tag_after == False, f"Actual: tag added in dry run, Expected: no changes in dry run"
        assert has_make_before == False, "Make should not exist before"
        assert has_make_after == False, f"Actual: EXIF added in dry run, Expected: no changes in dry run"

    def test_apply_mode_adds_tags(self, test_video):
        """Test that apply mode adds tags

        Actual: Tags added to file
        Expected: Both test-tag and another-tag present
        """
        # Record before state
        tag_result_before = subprocess.run([
            "tag", "--list", "--no-name", test_video
        ], capture_output=True, text=True)
        has_test_tag_before = "test-tag" in tag_result_before.stdout
        has_another_tag_before = "another-tag" in tag_result_before.stdout

        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--tags", "test-tag,another-tag",
            "--apply"
        ], capture_output=True, text=True)

        # Record after state
        tag_result_after = subprocess.run([
            "tag", "--list", "--no-name", test_video
        ], capture_output=True, text=True, check=True)
        has_test_tag_after = "test-tag" in tag_result_after.stdout
        has_another_tag_after = "another-tag" in tag_result_after.stdout

        # Verify behavior: tags should be added
        assert result.returncode == 0, f"Script should succeed: {result.stderr}"
        assert has_test_tag_before == False, "test-tag should not exist before"
        assert has_another_tag_before == False, "another-tag should not exist before"
        assert has_test_tag_after == True, f"Actual: test-tag not added, Expected: test-tag present"
        assert has_another_tag_after == True, f"Actual: another-tag not added, Expected: another-tag present"

    def test_apply_mode_adds_exif(self, test_video):
        """Test that apply mode adds EXIF data

        Actual: EXIF fields added to file
        Expected: Make=GoPro, Model=HERO12 Black
        """
        # Record before state
        exif_result_before = subprocess.run([
            "exiftool", "-s", "-Make", "-Model", test_video
        ], capture_output=True, text=True)
        has_make_before = "GoPro" in exif_result_before.stdout
        has_model_before = "HERO12 Black" in exif_result_before.stdout

        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--make", "GoPro",
            "--model", "HERO12 Black",
            "--apply"
        ], capture_output=True, text=True)

        # Record after state
        exif_result_after = subprocess.run([
            "exiftool", "-s", "-Make", "-Model", test_video
        ], capture_output=True, text=True, check=True)
        has_make_after = "GoPro" in exif_result_after.stdout
        has_model_after = "HERO12 Black" in exif_result_after.stdout

        # Verify behavior: EXIF should be added
        assert result.returncode == 0, f"Script should succeed: {result.stderr}"
        assert has_make_before == False, "Make should not exist before"
        assert has_model_before == False, "Model should not exist before"
        assert has_make_after == True, f"Actual: Make not added, Expected: Make=GoPro"
        assert has_model_after == True, f"Actual: Model not added, Expected: Model=HERO12 Black"

    def test_idempotency_tags(self, test_video):
        """Test that adding same tags twice doesn't duplicate

        Actual: Tag count stays at 1 after second run
        Expected: Idempotent, tag appears exactly once
        """
        # First run
        subprocess.run([
            sys.executable, str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--tags", "test-tag",
            "--apply"
        ], capture_output=True, check=True)

        # Verify tag was added once
        tag_result_after_first = subprocess.run([
            "tag", "--list", "--no-name", test_video
        ], capture_output=True, text=True, check=True)
        count_after_first = tag_result_after_first.stdout.count("test-tag")

        # Second run
        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--tags", "test-tag",
            "--apply"
        ], capture_output=True, text=True)

        # Verify tag wasn't duplicated
        tag_result_after_second = subprocess.run([
            "tag", "--list", "--no-name", test_video
        ], capture_output=True, text=True, check=True)
        count_after_second = tag_result_after_second.stdout.count("test-tag")

        # Verify idempotent behavior
        assert result.returncode == 0, f"Script should succeed: {result.stderr}"
        assert count_after_first == 1, "Tag should appear once after first run"
        assert count_after_second == 1, f"Actual: tag appears {count_after_second} times, Expected: tag appears exactly once (idempotent)"

    def test_idempotency_exif(self, test_video):
        """Test that setting same EXIF twice doesn't rewrite

        Actual: Modification time unchanged after second run
        Expected: Idempotent, no file write on second run
        """
        # First run
        subprocess.run([
            sys.executable, str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--make", "GoPro",
            "--model", "HERO12 Black",
            "--apply"
        ], capture_output=True, check=True)

        # Verify EXIF was written
        exif_result_after_first = subprocess.run([
            "exiftool", "-s", "-Make", "-Model", test_video
        ], capture_output=True, text=True, check=True)
        has_make_after_first = "GoPro" in exif_result_after_first.stdout
        has_model_after_first = "HERO12 Black" in exif_result_after_first.stdout

        # Get modification time after first run
        mtime_after_first = os.stat(test_video).st_mtime

        # Second run
        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--make", "GoPro",
            "--model", "HERO12 Black",
            "--apply"
        ], capture_output=True, text=True)

        # Verify EXIF unchanged
        exif_result_after_second = subprocess.run([
            "exiftool", "-s", "-Make", "-Model", test_video
        ], capture_output=True, text=True, check=True)
        has_make_after_second = "GoPro" in exif_result_after_second.stdout
        has_model_after_second = "HERO12 Black" in exif_result_after_second.stdout

        # Modification time shouldn't change (no exiftool write)
        mtime_after_second = os.stat(test_video).st_mtime

        # Verify idempotent behavior
        assert result.returncode == 0, f"Script should succeed: {result.stderr}"
        assert has_make_after_first == True and has_model_after_first == True, "EXIF should be set after first run"
        assert has_make_after_second == True and has_model_after_second == True, "EXIF should still be set after second run"
        assert abs(mtime_after_second - mtime_after_first) < 1, f"Actual: file was modified (mtime changed), Expected: no file write on idempotent second run"

    def test_partial_update_tags(self, test_video):
        """Test that only missing tags are added

        Actual: Both tags present, new-tag added after existing-tag
        Expected: Only new-tag added on second run (partial update)
        """
        # Add first tag
        subprocess.run([
            sys.executable, str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--tags", "existing-tag",
            "--apply"
        ], capture_output=True, check=True)

        # Verify first tag was added
        tag_result_after_first = subprocess.run([
            "tag", "--list", "--no-name", test_video
        ], capture_output=True, text=True, check=True)
        has_existing_tag_after_first = "existing-tag" in tag_result_after_first.stdout
        has_new_tag_after_first = "new-tag" in tag_result_after_first.stdout

        # Add second tag (first should be skipped)
        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--tags", "existing-tag,new-tag",
            "--apply"
        ], capture_output=True, text=True)

        # Verify both tags present
        tag_result_after_second = subprocess.run([
            "tag", "--list", "--no-name", test_video
        ], capture_output=True, text=True, check=True)
        has_existing_tag_after_second = "existing-tag" in tag_result_after_second.stdout
        has_new_tag_after_second = "new-tag" in tag_result_after_second.stdout

        # Verify partial update behavior
        assert result.returncode == 0, f"Script should succeed: {result.stderr}"
        assert has_existing_tag_after_first == True, "existing-tag should be added in first run"
        assert has_new_tag_after_first == False, "new-tag should not exist after first run"
        assert has_existing_tag_after_second == True, "existing-tag should still be present"
        assert has_new_tag_after_second == True, f"Actual: new-tag not added, Expected: new-tag added in second run (partial update)"

    def test_partial_update_exif(self, test_video):
        """Test that only missing EXIF fields are updated

        Actual: Both Make and Model present after second run
        Expected: Only Model added in second run (partial update)
        """
        # Set Make only
        subprocess.run([
            sys.executable, str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--make", "GoPro",
            "--apply"
        ], capture_output=True, check=True)

        # Verify Make was added
        exif_result_after_first = subprocess.run([
            "exiftool", "-s", "-Make", "-Model", test_video
        ], capture_output=True, text=True, check=True)
        has_make_after_first = "GoPro" in exif_result_after_first.stdout
        has_model_after_first = "HERO12 Black" in exif_result_after_first.stdout

        # Set both Make and Model (only Model should be written)
        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--make", "GoPro",
            "--model", "HERO12 Black",
            "--apply"
        ], capture_output=True, text=True)

        # Verify both present
        exif_result_after_second = subprocess.run([
            "exiftool", "-s", "-Make", "-Model", test_video
        ], capture_output=True, text=True, check=True)
        has_make_after_second = "GoPro" in exif_result_after_second.stdout
        has_model_after_second = "HERO12 Black" in exif_result_after_second.stdout

        # Verify partial update behavior
        assert result.returncode == 0, f"Script should succeed: {result.stderr}"
        assert has_make_after_first == True, "Make should be added in first run"
        assert has_model_after_first == False, "Model should not exist after first run"
        assert has_make_after_second == True, "Make should still be present"
        assert has_model_after_second == True, f"Actual: Model not added, Expected: Model added in second run (partial update)"

    def test_multiple_files(self, temp_dir):
        """Test processing multiple files"""
        videos = []
        for i in range(3):
            video_path = os.path.join(temp_dir, f"test_{i}.mp4")
            create_test_video(video_path)
            videos.append(video_path)

        # Process all files at once
        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "tag-media.py"),
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
        """Test that unsupported file types are handled gracefully

        Actual: .lrv file gets tags but not EXIF
        Expected: Tags added, EXIF skipped for unsupported type
        """
        mp4_path = os.path.join(temp_dir, "test.mp4")
        create_test_video(mp4_path)

        # Rename to .lrv
        lrv_path = os.path.join(temp_dir, "test.lrv")
        shutil.move(mp4_path, lrv_path)

        # Record before state
        tag_result_before = subprocess.run([
            "tag", "--list", "--no-name", lrv_path
        ], capture_output=True, text=True)
        has_tag_before = "test-tag" in tag_result_before.stdout

        exif_result_before = subprocess.run([
            "exiftool", "-s", "-Make", lrv_path
        ], capture_output=True, text=True)
        has_make_before = "GoPro" in exif_result_before.stdout

        # Should skip EXIF for .lrv but still allow tags
        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "tag-media.py"),
            lrv_path,
            "--make", "GoPro",
            "--tags", "test-tag",
            "--apply"
        ], capture_output=True, text=True)

        # Record after state
        tag_result_after = subprocess.run([
            "tag", "--list", "--no-name", lrv_path
        ], capture_output=True, text=True, check=True)
        has_tag_after = "test-tag" in tag_result_after.stdout

        exif_result_after = subprocess.run([
            "exiftool", "-s", "-Make", lrv_path
        ], capture_output=True, text=True)
        has_make_after = "GoPro" in exif_result_after.stdout

        # Verify behavior: tags should be added, EXIF should be skipped for .lrv
        assert result.returncode == 0, f"Script should succeed: {result.stderr}"
        assert has_tag_before == False, "Tag should not exist before"
        assert has_tag_after == True, f"Actual: tag not added to .lrv file, Expected: test-tag added despite unsupported type"
        assert has_make_before == False, "Make should not exist before"
        assert has_make_after == False, f"Actual: EXIF Make added to .lrv file, Expected: EXIF skipped for unsupported .lrv type"

    def test_output_format(self, test_video):
        """Test that output follows presentation format"""
        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "tag-media.py"),
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
        """Test adding both tags and EXIF together

        Actual: Both tags and EXIF added
        Expected: Tag and EXIF metadata present on file
        """
        # Record before state
        tag_result_before = subprocess.run([
            "tag", "--list", "--no-name", test_video
        ], capture_output=True, text=True)
        has_tag_before = "gopro-hero-12" in tag_result_before.stdout

        exif_result_before = subprocess.run([
            "exiftool", "-s", "-Make", "-Model", test_video
        ], capture_output=True, text=True)
        has_make_before = "GoPro" in exif_result_before.stdout
        has_model_before = "HERO12 Black" in exif_result_before.stdout

        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--tags", "gopro-hero-12",
            "--make", "GoPro",
            "--model", "HERO12 Black",
            "--apply"
        ], capture_output=True, text=True)

        # Verify both were added
        tag_result_after = subprocess.run([
            "tag", "--list", "--no-name", test_video
        ], capture_output=True, text=True, check=True)
        has_tag_after = "gopro-hero-12" in tag_result_after.stdout

        exif_result_after = subprocess.run([
            "exiftool", "-s", "-Make", "-Model", test_video
        ], capture_output=True, text=True, check=True)
        has_make_after = "GoPro" in exif_result_after.stdout
        has_model_after = "HERO12 Black" in exif_result_after.stdout

        # Verify combined behavior
        assert result.returncode == 0, f"Script should succeed: {result.stderr}"
        assert has_tag_before == False, "Tag should not exist before"
        assert has_make_before == False, "Make should not exist before"
        assert has_model_before == False, "Model should not exist before"
        assert has_tag_after == True, f"Actual: tag not added, Expected: gopro-hero-12 tag present"
        assert has_make_after == True, f"Actual: Make not added, Expected: Make=GoPro"
        assert has_model_after == True, f"Actual: Model not added, Expected: Model=HERO12 Black"


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
        create_test_video(video_path)
        return video_path

    def test_returns_what_changed(self, test_video):
        """Test that functions return data about what changed"""
        # This tests the principle from CLAUDE.md:
        # "separation of data and presentation"
        # Functions should return what changed, presentation formats it

        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "tag-media.py"),
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
            sys.executable, str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--tags", "test-tag",
            "--apply"
        ], capture_output=True, check=True)

        # Run again - should report already correct
        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "tag-media.py"),
            test_video,
            "--tags", "test-tag",
            "--apply"
        ], capture_output=True, text=True)

        assert "Already tagged correctly" in result.stdout
        # Should NOT say it tagged anything
        assert "Tagged:" not in result.stdout or "Already" in result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
