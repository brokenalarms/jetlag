#!/usr/bin/env python3
"""
Tests for ingest-media.py

Covers: apply copies file, dry-run no-op, flat copy from subdirectory,
missing source file error.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPT = str(Path(__file__).parent.parent / "ingest-media.py")


def run_ingest(*args: str) -> subprocess.CompletedProcess:
    """Run ingest-media.py with the given arguments."""
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True,
        text=True,
    )


class TestApplyMode:
    """--apply copies file to working dir, source unchanged."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.source_dir = os.path.join(self.temp_dir, "source")
        self.working_dir = os.path.join(self.temp_dir, "working")
        os.makedirs(self.source_dir)
        self.source_file = os.path.join(self.source_dir, "GH010001.MP4")
        Path(self.source_file).write_bytes(b"video-data")

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)

    def test_file_copied_to_working_dir(self):
        """Source file is copied into working dir."""
        result = run_ingest(self.source_file, "--target", self.working_dir, "--apply")

        assert result.returncode == 0
        dest = os.path.join(self.working_dir, "GH010001.MP4")
        assert os.path.exists(dest), "File should exist in working dir"
        assert Path(dest).read_bytes() == b"video-data"

    def test_source_file_unchanged(self):
        """Source file remains intact after copy."""
        run_ingest(self.source_file, "--target", self.working_dir, "--apply")

        assert os.path.exists(self.source_file), "Source file should still exist"
        assert Path(self.source_file).read_bytes() == b"video-data"

    def test_machine_output(self):
        """Correct @@dest and @@action emitted on stdout."""
        result = run_ingest(self.source_file, "--target", self.working_dir, "--apply")

        expected_dest = os.path.join(self.working_dir, "GH010001.MP4")
        assert f"@@dest={expected_dest}" in result.stdout
        assert "@@action=copied" in result.stdout


class TestDryRun:
    """Without --apply, no file is created."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.source_dir = os.path.join(self.temp_dir, "source")
        self.working_dir = os.path.join(self.temp_dir, "working")
        os.makedirs(self.source_dir)
        self.source_file = os.path.join(self.source_dir, "GH010001.MP4")
        Path(self.source_file).write_bytes(b"video-data")

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)

    def test_no_file_created(self):
        """Dry run does not create file in working dir."""
        result = run_ingest(self.source_file, "--target", self.working_dir)

        assert result.returncode == 0
        assert not os.path.exists(self.working_dir), "Working dir should not be created"

    def test_dry_run_output(self):
        """Dry run reports what would happen."""
        result = run_ingest(self.source_file, "--target", self.working_dir)

        assert "Would copy" in result.stderr
        assert "@@action=would_copy" in result.stdout


class TestFlatCopy:
    """Source in subdirectory → copy is at root of working dir (not nested)."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.source_dir = os.path.join(self.temp_dir, "source")
        self.working_dir = os.path.join(self.temp_dir, "working")
        nested_dir = os.path.join(self.source_dir, "100GOPRO", "sub")
        os.makedirs(nested_dir)
        self.source_file = os.path.join(nested_dir, "GH010001.MP4")
        Path(self.source_file).write_bytes(b"video-data")

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)

    def test_flat_copy_no_nesting(self):
        """File from nested source lands at root of working dir."""
        result = run_ingest(self.source_file, "--target", self.working_dir, "--apply")

        assert result.returncode == 0
        flat_dest = os.path.join(self.working_dir, "GH010001.MP4")
        nested_dest = os.path.join(self.working_dir, "100GOPRO", "sub", "GH010001.MP4")
        assert os.path.exists(flat_dest), "File should be at root of working dir"
        assert not os.path.exists(nested_dest), "File should not preserve source nesting"


class TestErrorHandling:
    """Missing source file → non-zero exit."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.working_dir = os.path.join(self.temp_dir, "working")

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)

    def test_missing_source_file(self):
        """Non-existent source file exits non-zero."""
        result = run_ingest("/nonexistent/file.mp4", "--target", self.working_dir, "--apply")

        assert result.returncode != 0
        assert "ERROR" in result.stderr
