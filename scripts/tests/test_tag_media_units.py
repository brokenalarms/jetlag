#!/usr/bin/env python3
"""
Unit tests for tag-media.py
Tests individual functions focusing on data rather than presentation
"""

import os
import sys
import tempfile
import shutil
import subprocess
from pathlib import Path
import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import hyphenated module name
import importlib.util
spec = importlib.util.spec_from_file_location(
    "tag_media",
    str(Path(__file__).parent.parent / "tag-media.py")
)
tm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tm)


@pytest.mark.skipif(sys.platform != "darwin", reason="requires macOS — Finder tags don't exist on Linux")
class TestGetExistingTags:
    """Test get_existing_finder_tags function"""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_video = os.path.join(self.temp_dir, "test.mp4")

        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            self.test_video
        ], capture_output=True, check=True)

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)

    def test_get_existing_tags_empty(self):
        """Test getting tags from file with no tags"""
        tags = tm.get_existing_finder_tags(self.test_video)

        assert isinstance(tags, list)
        assert len(tags) == 0

    def test_get_existing_tags_with_tags(self):
        """Test getting tags from file with existing tags"""
        # Add tags
        subprocess.run([
            "tag", "--add", "test-tag", self.test_video
        ], capture_output=True, check=True)

        subprocess.run([
            "tag", "--add", "another-tag", self.test_video
        ], capture_output=True, check=True)

        tags = tm.get_existing_finder_tags(self.test_video)

        assert isinstance(tags, list)
        assert len(tags) == 2
        assert "test-tag" in tags
        assert "another-tag" in tags

    def test_get_existing_tags_nonexistent_file(self):
        """Test getting tags from nonexistent file"""
        tags = tm.get_existing_finder_tags("/nonexistent/file.mp4")

        assert isinstance(tags, list)
        assert len(tags) == 0  # Should return empty list, not error


@pytest.mark.skipif(sys.platform != "darwin", reason="requires macOS — Finder tags don't exist on Linux")
class TestApplyFinderTags:
    """Test apply_finder_tags function - focus on return values"""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_video = os.path.join(self.temp_dir, "test.mp4")

        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            self.test_video
        ], capture_output=True, check=True)

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)

    def test_apply_finder_tags_returns_added_tags(self):
        """Test that function returns list of tags actually added"""
        success, tags_added = tm.apply_finder_tags(
            self.test_video,
            ["tag1", "tag2"],
            dry_run=False
        )

        assert success is True
        assert isinstance(tags_added, list)
        assert len(tags_added) == 2
        assert "tag1" in tags_added
        assert "tag2" in tags_added

    def test_apply_finder_tags_skips_existing(self):
        """Test that function skips existing tags"""
        # Add one tag
        subprocess.run([
            "tag", "--add", "existing-tag", self.test_video
        ], capture_output=True, check=True)

        # Try to add existing + new
        success, tags_added = tm.apply_finder_tags(
            self.test_video,
            ["existing-tag", "new-tag"],
            dry_run=False
        )

        assert success is True
        # Should only add new-tag
        assert len(tags_added) == 1
        assert "new-tag" in tags_added
        assert "existing-tag" not in tags_added

    def test_apply_finder_tags_dry_run(self):
        """Test that dry run returns data but doesn't modify file"""
        success, tags_added = tm.apply_finder_tags(
            self.test_video,
            ["tag1", "tag2"],
            dry_run=True
        )

        assert success is True
        # Should return what WOULD be added
        assert len(tags_added) == 2

        # But tags shouldn't actually be on file
        actual_tags = tm.get_existing_finder_tags(self.test_video)
        assert len(actual_tags) == 0

    def test_apply_finder_tags_empty_list(self):
        """Test handling empty tag list"""
        success, tags_added = tm.apply_finder_tags(
            self.test_video,
            [],
            dry_run=False
        )

        assert success is True
        assert len(tags_added) == 0

    def test_apply_finder_tags_all_existing(self):
        """Test when all tags already exist"""
        # Add tags
        subprocess.run([
            "tag", "--add", "tag1", self.test_video
        ], capture_output=True, check=True)

        # Try to add same tag
        success, tags_added = tm.apply_finder_tags(
            self.test_video,
            ["tag1"],
            dry_run=False
        )

        assert success is True
        assert len(tags_added) == 0  # Nothing added


class TestGetExistingExifCamera:
    """Test get_existing_exif_camera function"""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_video = os.path.join(self.temp_dir, "test.mp4")

        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            self.test_video
        ], capture_output=True, check=True)

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)

    def test_get_existing_exif_empty(self):
        """Test getting EXIF from file with no camera data"""
        data = tm.get_existing_exif_camera(self.test_video)

        assert isinstance(data, dict)
        # May be empty or have some default fields
        assert "Make" not in data or data.get("Make") == ""

    def test_get_existing_exif_with_data(self):
        """Test getting EXIF from file with camera data"""
        # Set EXIF
        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            "-Make=GoPro",
            "-Model=HERO12 Black",
            self.test_video
        ], capture_output=True, check=True)

        data = tm.get_existing_exif_camera(self.test_video)

        assert isinstance(data, dict)
        assert data.get("Make") == "GoPro"
        assert data.get("Model") == "HERO12 Black"


class TestAddCameraToExif:
    """Test add_camera_to_exif function - focus on return values"""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_video = os.path.join(self.temp_dir, "test.mp4")

        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            self.test_video
        ], capture_output=True, check=True)

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)

    def test_add_camera_returns_fields_updated(self):
        """Test that function returns which fields were updated"""
        success, fields_updated = tm.add_camera_to_exif(
            self.test_video,
            make="GoPro",
            model="HERO12 Black",
            dry_run=False
        )

        assert success is True
        assert isinstance(fields_updated, list)
        assert len(fields_updated) == 2
        assert "Make" in fields_updated
        assert "Model" in fields_updated

    def test_add_camera_skips_existing(self):
        """Test that existing fields are skipped"""
        # Set Make only
        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            "-Make=GoPro",
            self.test_video
        ], capture_output=True, check=True)

        # Add both Make and Model
        success, fields_updated = tm.add_camera_to_exif(
            self.test_video,
            make="GoPro",
            model="HERO12 Black",
            dry_run=False
        )

        assert success is True
        # Should only update Model
        assert len(fields_updated) == 1
        assert "Model" in fields_updated
        assert "Make" not in fields_updated

    def test_add_camera_dry_run(self):
        """Test that dry run returns data but doesn't modify file"""
        success, fields_updated = tm.add_camera_to_exif(
            self.test_video,
            make="GoPro",
            model="HERO12 Black",
            dry_run=True
        )

        assert success is True
        # Should return what WOULD be updated
        assert len(fields_updated) == 2

        # But file shouldn't be modified
        data = tm.get_existing_exif_camera(self.test_video)
        assert data.get("Make") != "GoPro"

    def test_add_camera_make_only(self):
        """Test adding only Make"""
        success, fields_updated = tm.add_camera_to_exif(
            self.test_video,
            make="GoPro",
            model=None,
            dry_run=False
        )

        assert success is True
        assert len(fields_updated) == 1
        assert "Make" in fields_updated

    def test_add_camera_model_only(self):
        """Test adding only Model"""
        success, fields_updated = tm.add_camera_to_exif(
            self.test_video,
            make=None,
            model="HERO12 Black",
            dry_run=False
        )

        assert success is True
        assert len(fields_updated) == 1
        assert "Model" in fields_updated

    def test_add_camera_none_needed(self):
        """Test when no fields need updating"""
        # Set both fields
        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            "-Make=GoPro",
            "-Model=HERO12 Black",
            self.test_video
        ], capture_output=True, check=True)

        # Try to set same values
        success, fields_updated = tm.add_camera_to_exif(
            self.test_video,
            make="GoPro",
            model="HERO12 Black",
            dry_run=False
        )

        assert success is True
        assert len(fields_updated) == 0

    def test_add_camera_empty_params(self):
        """Test with no make or model"""
        success, fields_updated = tm.add_camera_to_exif(
            self.test_video,
            make=None,
            model=None,
            dry_run=False
        )

        assert success is True
        assert len(fields_updated) == 0

    def test_add_camera_unsupported_extension(self):
        """Test that unsupported file types are skipped"""
        lrv_path = os.path.join(self.temp_dir, "test.lrv")
        shutil.copy(self.test_video, lrv_path)

        success, fields_updated = tm.add_camera_to_exif(
            lrv_path,
            make="GoPro",
            model="HERO12",
            dry_run=False
        )

        assert success is True
        # Should skip unsupported type
        assert len(fields_updated) == 0


@pytest.mark.skipif(sys.platform != "darwin", reason="requires macOS — Finder tags don't exist on Linux")
class TestIdempotency:
    """Test idempotency - running twice should not change anything second time"""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_video = os.path.join(self.temp_dir, "test.mp4")

        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            self.test_video
        ], capture_output=True, check=True)

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)

    def test_tags_idempotent(self):
        """Test that applying tags twice is idempotent"""
        # First application
        success1, added1 = tm.apply_finder_tags(
            self.test_video,
            ["tag1", "tag2"],
            dry_run=False
        )

        assert success1 is True
        assert len(added1) == 2

        # Second application
        success2, added2 = tm.apply_finder_tags(
            self.test_video,
            ["tag1", "tag2"],
            dry_run=False
        )

        assert success2 is True
        assert len(added2) == 0  # Nothing to add

    def test_exif_idempotent(self):
        """Test that applying EXIF twice is idempotent"""
        # First application
        success1, updated1 = tm.add_camera_to_exif(
            self.test_video,
            make="GoPro",
            model="HERO12",
            dry_run=False
        )

        assert success1 is True
        assert len(updated1) == 2

        # Get mtime after first write
        mtime1 = os.stat(self.test_video).st_mtime

        # Second application
        success2, updated2 = tm.add_camera_to_exif(
            self.test_video,
            make="GoPro",
            model="HERO12",
            dry_run=False
        )

        assert success2 is True
        assert len(updated2) == 0  # Nothing to update

        # File shouldn't be modified
        mtime2 = os.stat(self.test_video).st_mtime
        assert abs(mtime2 - mtime1) < 1  # Within 1 second


@pytest.mark.skipif(sys.platform != "darwin", reason="requires macOS — Finder tags don't exist on Linux")
class TestDataPresentation:
    """Test data/presentation separation principle"""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_video = os.path.join(self.temp_dir, "test.mp4")

        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            self.test_video
        ], capture_output=True, check=True)

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)

    def test_functions_return_data_not_strings(self):
        """Test that core functions return structured data, not formatted strings"""
        # apply_finder_tags returns (bool, List[str])
        success, tags_added = tm.apply_finder_tags(
            self.test_video,
            ["tag1"],
            dry_run=True
        )

        assert isinstance(success, bool)
        assert isinstance(tags_added, list)
        # Not a formatted string
        assert all(isinstance(tag, str) for tag in tags_added)

        # add_camera_to_exif returns (bool, List[str])
        success, fields_updated = tm.add_camera_to_exif(
            self.test_video,
            make="GoPro",
            dry_run=True
        )

        assert isinstance(success, bool)
        assert isinstance(fields_updated, list)
        assert all(isinstance(field, str) for field in fields_updated)

    def test_read_functions_return_raw_data(self):
        """Test that read functions return raw data structures"""
        # get_existing_finder_tags returns List[str]
        tags = tm.get_existing_finder_tags(self.test_video)
        assert isinstance(tags, list)

        # get_existing_exif_camera returns dict
        exif = tm.get_existing_exif_camera(self.test_video)
        assert isinstance(exif, dict)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
