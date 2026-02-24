#!/usr/bin/env python3
"""
Tests for archive-source.py

Covers: leave no-op, archive rename, delete only passed files,
empty dir cleanup, non-empty dir preservation, read-only source error,
dry-run no-op.
"""

import os
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

SCRIPT = str(Path(__file__).parent.parent / "archive-source.py")

NOT_ROOT = os.getuid() != 0


def run_archive_source(*args: str) -> subprocess.CompletedProcess:
    """Run archive-source.py with the given arguments."""
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True,
        text=True,
    )


class TestLeave:
    """--action leave is a no-op: source folder and files are untouched."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.source = os.path.join(self.temp_dir, "DCIM")
        os.makedirs(self.source)
        self.file_a = os.path.join(self.source, "IMG_001.MP4")
        Path(self.file_a).write_bytes(b"video-a")

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)

    def test_leave_preserves_source(self):
        """Source directory and all files remain after leave action."""
        before_files = set(os.listdir(self.source))

        result = run_archive_source("--source", self.source, "--action", "leave", "--apply")

        assert result.returncode == 0
        assert os.path.isdir(self.source)
        assert set(os.listdir(self.source)) == before_files

    def test_leave_is_default_action(self):
        """When no --action is specified, leave is the default."""
        result = run_archive_source("--source", self.source, "--apply")

        assert result.returncode == 0
        assert os.path.isdir(self.source)
        assert Path(self.file_a).read_bytes() == b"video-a"


class TestArchive:
    """--action archive renames the source folder."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.source = os.path.join(self.temp_dir, "DCIM")
        os.makedirs(self.source)
        self.file_a = os.path.join(self.source, "IMG_001.MP4")
        self.file_b = os.path.join(self.source, "sub", "IMG_002.MP4")
        Path(self.file_a).write_bytes(b"video-a")
        os.makedirs(os.path.dirname(self.file_b))
        Path(self.file_b).write_bytes(b"video-b")

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)

    def test_archive_renames_source_folder(self):
        """Source folder is renamed to '<source> - archived <date>'."""
        result = run_archive_source("--source", self.source, "--action", "archive", "--apply")

        assert result.returncode == 0

        today = datetime.now().strftime("%Y-%m-%d")
        expected_name = f"DCIM - archived {today}"
        archived_path = os.path.join(self.temp_dir, expected_name)

        assert os.path.isdir(archived_path), f"Expected archived folder: {expected_name}"
        assert not os.path.exists(self.source), "Original source should no longer exist"

    def test_archive_preserves_all_contents(self):
        """All files and subdirectories survive the rename."""
        run_archive_source("--source", self.source, "--action", "archive", "--apply")

        today = datetime.now().strftime("%Y-%m-%d")
        archived_path = os.path.join(self.temp_dir, f"DCIM - archived {today}")

        assert Path(os.path.join(archived_path, "IMG_001.MP4")).read_bytes() == b"video-a"
        assert Path(os.path.join(archived_path, "sub", "IMG_002.MP4")).read_bytes() == b"video-b"


class TestDelete:
    """--action delete removes only passed files and cleans empty dirs."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.source = os.path.join(self.temp_dir, "DCIM")
        os.makedirs(self.source)

        # Create files in nested structure
        self.file_a = os.path.join(self.source, "100GOPRO", "GH010001.MP4")
        self.file_b = os.path.join(self.source, "100GOPRO", "GH010001.LRV")
        self.file_c = os.path.join(self.source, "100GOPRO", "GH010002.MP4")
        self.file_d = os.path.join(self.source, "101GOPRO", "GH020001.MP4")

        for f in [self.file_a, self.file_b, self.file_c, self.file_d]:
            os.makedirs(os.path.dirname(f), exist_ok=True)
            Path(f).write_bytes(b"data")

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)

    def test_delete_only_passed_files(self):
        """Only files listed in --files are removed; others survive."""
        result = run_archive_source(
            "--source", self.source,
            "--action", "delete",
            "--files", self.file_a, self.file_b,
            "--apply",
        )

        assert result.returncode == 0
        assert not os.path.exists(self.file_a), "Passed file should be deleted"
        assert not os.path.exists(self.file_b), "Passed companion should be deleted"
        assert os.path.exists(self.file_c), "Unpassed file in same dir should survive"
        assert os.path.exists(self.file_d), "File in other dir should survive"

    def test_delete_cleans_empty_dirs(self):
        """After deleting all files in a subdir, the empty subdir is removed."""
        result = run_archive_source(
            "--source", self.source,
            "--action", "delete",
            "--files", self.file_d,
            "--apply",
        )

        assert result.returncode == 0
        assert not os.path.exists(self.file_d)
        assert not os.path.exists(os.path.join(self.source, "101GOPRO")), \
            "Empty 101GOPRO directory should be removed"

    def test_delete_preserves_non_empty_dirs(self):
        """Directories with remaining files are not removed."""
        result = run_archive_source(
            "--source", self.source,
            "--action", "delete",
            "--files", self.file_a,
            "--apply",
        )

        assert result.returncode == 0
        assert not os.path.exists(self.file_a)
        assert os.path.isdir(os.path.join(self.source, "100GOPRO")), \
            "100GOPRO still has files, should not be removed"
        assert os.path.exists(self.file_b)
        assert os.path.exists(self.file_c)

    def test_delete_preserves_source_root(self):
        """Source root directory is never removed even if all files deleted."""
        all_files = [self.file_a, self.file_b, self.file_c, self.file_d]
        result = run_archive_source(
            "--source", self.source,
            "--action", "delete",
            "--files", *all_files,
            "--apply",
        )

        assert result.returncode == 0
        for f in all_files:
            assert not os.path.exists(f)
        assert not os.path.exists(os.path.join(self.source, "100GOPRO")), \
            "Empty subdirs should be removed"
        assert not os.path.exists(os.path.join(self.source, "101GOPRO")), \
            "Empty subdirs should be removed"

    def test_delete_main_and_companion_leaves_noncompanion(self):
        """Delete a .mp4 and its .thm companion; a non-companion in a
        nested subdir is left alone."""
        # Structure:
        #   source/foo/myfile.mp4       (passed to --files)
        #   source/foo/myfile.thm       (companion, passed to --files)
        #   source/foo/bar/leaveme.txt  (not passed, should survive)
        foo = os.path.join(self.source, "foo")
        bar = os.path.join(foo, "bar")
        os.makedirs(bar)

        main_file = os.path.join(foo, "myfile.mp4")
        companion = os.path.join(foo, "myfile.thm")
        unrelated = os.path.join(bar, "leaveme.txt")

        Path(main_file).write_bytes(b"video")
        Path(companion).write_bytes(b"thumb")
        Path(unrelated).write_bytes(b"keep-me")

        result = run_archive_source(
            "--source", self.source,
            "--action", "delete",
            "--files", main_file, companion,
            "--apply",
        )

        assert result.returncode == 0
        assert not os.path.exists(main_file), "Main file should be deleted"
        assert not os.path.exists(companion), "Companion should be deleted"
        assert os.path.exists(unrelated), "Non-companion in nested subdir should survive"
        assert os.path.isdir(bar), "bar/ has files, should not be removed"
        assert os.path.isdir(foo), "foo/ still has bar/ subdir, should not be removed"

    def test_delete_skips_already_missing_files(self):
        """Files that don't exist in --files are silently skipped."""
        missing = os.path.join(self.source, "100GOPRO", "GHOST.MP4")

        result = run_archive_source(
            "--source", self.source,
            "--action", "delete",
            "--files", missing, self.file_d,
            "--apply",
        )

        assert result.returncode == 0
        assert not os.path.exists(self.file_d)


class TestReadOnlySource:
    """Read-only source should log error and exit non-zero."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.source = os.path.join(self.temp_dir, "DCIM")
        os.makedirs(self.source)
        self.file_a = os.path.join(self.source, "IMG_001.MP4")
        Path(self.file_a).write_bytes(b"video")

    def teardown_method(self):
        # Restore write permissions for cleanup
        for root, dirs, files in os.walk(self.temp_dir):
            os.chmod(root, stat.S_IRWXU)
        shutil.rmtree(self.temp_dir)

    @pytest.mark.skipif(not NOT_ROOT, reason="root bypasses filesystem permissions")
    def test_archive_read_only_source_fails(self):
        """Archive action on read-only parent directory exits non-zero."""
        os.chmod(self.temp_dir, stat.S_IRUSR | stat.S_IXUSR)

        result = run_archive_source(
            "--source", self.source,
            "--action", "archive",
            "--apply",
        )

        os.chmod(self.temp_dir, stat.S_IRWXU)

        assert result.returncode != 0
        assert "couldn't archive" in result.stderr

    @pytest.mark.skipif(not NOT_ROOT, reason="root bypasses filesystem permissions")
    def test_delete_read_only_file_fails(self):
        """Delete action on read-only directory exits non-zero."""
        os.chmod(self.source, stat.S_IRUSR | stat.S_IXUSR)

        result = run_archive_source(
            "--source", self.source,
            "--action", "delete",
            "--files", self.file_a,
            "--apply",
        )

        os.chmod(self.source, stat.S_IRWXU)

        assert result.returncode != 0
        assert "couldn't delete" in result.stderr


class TestDryRun:
    """Without --apply, no changes should be made."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.source = os.path.join(self.temp_dir, "DCIM")
        os.makedirs(self.source)
        self.file_a = os.path.join(self.source, "IMG_001.MP4")
        Path(self.file_a).write_bytes(b"video")

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)

    def test_dry_run_archive_no_rename(self):
        """Dry run archive does not rename the source folder."""
        result = run_archive_source("--source", self.source, "--action", "archive")

        assert result.returncode == 0
        assert os.path.isdir(self.source), "Source should still exist in dry run"
        assert "Would rename" in result.stderr

    def test_dry_run_delete_no_removal(self):
        """Dry run delete does not remove any files."""
        result = run_archive_source(
            "--source", self.source,
            "--action", "delete",
            "--files", self.file_a,
        )

        assert result.returncode == 0
        assert os.path.exists(self.file_a), "File should still exist in dry run"
        assert "Would delete" in result.stderr
