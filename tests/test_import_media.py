#!/usr/bin/env python3
"""
Unit tests for import-media.py
Tests cleanup_empty_parent_dirs and source_dir profile loading.
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from lib.filesystem import cleanup_empty_parent_dirs

import importlib.util
spec = importlib.util.spec_from_file_location(
    "import_media",
    str(Path(__file__).parent.parent / "scripts" / "import-media.py")
)
im = importlib.util.module_from_spec(spec)
spec.loader.exec_module(im)


class TestCleanupEmptyParentDirs:

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)

    def test_removes_empty_subdirectories(self):
        """Empty subdirs within source are removed."""
        source = os.path.join(self.temp_dir, "PRIVATE")
        deep = os.path.join(source, "M4ROOT", "CLIP")
        os.makedirs(deep)

        cleanup_empty_parent_dirs(deep, stop_at=source)

        assert not os.path.exists(os.path.join(source, "M4ROOT", "CLIP"))
        assert not os.path.exists(os.path.join(source, "M4ROOT"))
        assert os.path.exists(source), "source_root must not be removed"

    def test_stops_before_source_root(self):
        """Never removes the stop_at directory itself."""
        source = os.path.join(self.temp_dir, "PRIVATE")
        os.makedirs(source)

        cleanup_empty_parent_dirs(source, stop_at=source)

        assert os.path.exists(source)

    def test_removes_ds_store_only_dirs(self):
        """.DS_Store is removed if it's the only thing preventing cleanup."""
        source = os.path.join(self.temp_dir, "PRIVATE")
        subdir = os.path.join(source, "M4ROOT")
        os.makedirs(subdir)
        Path(os.path.join(subdir, ".DS_Store")).write_bytes(b"fake")

        cleanup_empty_parent_dirs(subdir, stop_at=source)

        assert not os.path.exists(subdir)
        assert os.path.exists(source)

    def test_preserves_nonempty_directories(self):
        """Directories with real files are not removed."""
        source = os.path.join(self.temp_dir, "PRIVATE")
        subdir = os.path.join(source, "M4ROOT")
        os.makedirs(subdir)
        Path(os.path.join(subdir, "SONYCARD.IND")).write_bytes(b"data")

        cleanup_empty_parent_dirs(subdir, stop_at=source)

        assert os.path.exists(subdir)
        assert os.path.exists(os.path.join(subdir, "SONYCARD.IND"))

    def test_preserves_ds_store_when_other_files_exist(self):
        """.DS_Store is not removed if other files also exist."""
        source = os.path.join(self.temp_dir, "PRIVATE")
        subdir = os.path.join(source, "M4ROOT")
        os.makedirs(subdir)
        Path(os.path.join(subdir, ".DS_Store")).write_bytes(b"fake")
        Path(os.path.join(subdir, "real_file.xml")).write_bytes(b"data")

        cleanup_empty_parent_dirs(subdir, stop_at=source)

        assert os.path.exists(subdir)
        assert os.path.exists(os.path.join(subdir, ".DS_Store"))

    def test_never_removes_cwd(self):
        """Current working directory is never removed even if empty."""
        source = os.path.join(self.temp_dir, "PRIVATE")
        os.makedirs(source)

        original_cwd = os.getcwd()
        try:
            os.chdir(source)
            cleanup_empty_parent_dirs(source, stop_at=self.temp_dir)
        finally:
            os.chdir(original_cwd)

        assert os.path.exists(source)

    def test_partial_cleanup_stops_at_nonempty(self):
        """Removes empty leaf dirs but stops when hitting a dir with other contents."""
        source = os.path.join(self.temp_dir, "PRIVATE")
        branch_a = os.path.join(source, "M4ROOT", "CLIP")
        branch_b = os.path.join(source, "M4ROOT", "THMBNL")
        os.makedirs(branch_a)
        os.makedirs(branch_b)
        Path(os.path.join(branch_b, "thumb.jpg")).write_bytes(b"img")

        cleanup_empty_parent_dirs(branch_a, stop_at=source)

        assert not os.path.exists(branch_a), "Empty CLIP should be removed"
        assert os.path.exists(os.path.join(source, "M4ROOT")), "M4ROOT has THMBNL, should remain"
        assert os.path.exists(branch_b), "THMBNL with files should remain"


class TestSourceDirProfileLoading:

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)

    def _write_profiles(self, profiles_data: dict) -> str:
        import yaml
        path = os.path.join(self.temp_dir, "profiles.yaml")
        with open(path, 'w') as f:
            yaml.dump({"profiles": profiles_data}, f)
        return path

    def test_source_dir_loaded_from_profile(self):
        """source_dir field is loaded into ImportProfile."""
        path = self._write_profiles({
            "test": {
                "import_dir": "/tmp/import",
                "source_dir": "PRIVATE",
                "file_extensions": [".mp4"],
            }
        })
        profiles = im.load_profiles(path)
        assert profiles["test"].source_dir == "PRIVATE"

    def test_source_dir_none_when_missing(self):
        """source_dir is None when not specified in profile."""
        path = self._write_profiles({
            "test": {
                "import_dir": "/tmp/import",
                "file_extensions": [".mp4"],
            }
        })
        profiles = im.load_profiles(path)
        assert profiles["test"].source_dir is None

    def test_find_source_uses_profile_source_dir(self):
        """Profile's source_dir is used when user doesn't specify one."""
        source = os.path.join(self.temp_dir, "PRIVATE")
        os.makedirs(source)

        original_cwd = os.getcwd()
        try:
            os.chdir(self.temp_dir)
            result = im.find_source_directory("PRIVATE")
            assert result == "PRIVATE"
        finally:
            os.chdir(original_cwd)

    def test_user_override_takes_precedence(self):
        """User-specified source_dir overrides profile."""
        source = os.path.join(self.temp_dir, "DCIM")
        os.makedirs(source)

        original_cwd = os.getcwd()
        try:
            os.chdir(self.temp_dir)
            result = im.find_source_directory("DCIM")
            assert result == "DCIM"
        finally:
            os.chdir(original_cwd)

    def test_missing_source_dir_raises(self):
        """Non-existent source_dir raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            im.find_source_directory("NONEXISTENT")
