#!/usr/bin/env python3
"""
Tests for report-file-dates.py
Validates pre-flight scanner output.
"""

import os
import sys
import tempfile
import shutil
import subprocess
from pathlib import Path
import pytest

from conftest import create_test_video

SCRIPT_DIR = Path(__file__).parent.parent


def _parse_at_lines(stdout: str) -> dict:
    result = {}
    for line in stdout.strip().split("\n"):
        if line.startswith("@@"):
            key_value = line[2:]
            if "=" in key_value:
                key, value = key_value.split("=", 1)
                result[key] = value
    return result


class TestReportFileDates:

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)

    def test_all_parseable(self):
        """Folder where all files have parseable dates."""
        create_test_video(os.path.join(self.temp_dir, "VID_20250505_130334.mp4"))
        create_test_video(os.path.join(self.temp_dir, "VID_20250506_140000.mp4"))

        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "report-file-dates.py"),
            self.temp_dir,
            "--file-extensions", ".mp4"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        at = _parse_at_lines(result.stdout)
        assert at["all_parseable"] == "true"
        assert at["parseable_count"] == "2"
        assert at["total_count"] == "2"

    def test_mixed_folder(self):
        """Mixed folder — some parseable, some not."""
        create_test_video(os.path.join(self.temp_dir, "VID_20250505_130334.mp4"))
        create_test_video(os.path.join(self.temp_dir, "random_file.mp4"))

        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "report-file-dates.py"),
            self.temp_dir,
            "--file-extensions", ".mp4"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        at = _parse_at_lines(result.stdout)
        assert at["all_parseable"] == "false"
        assert at["parseable_count"] == "1"
        assert at["total_count"] == "2"

    def test_empty_folder(self):
        """Empty folder — graceful no-op."""
        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "report-file-dates.py"),
            self.temp_dir,
            "--file-extensions", ".mp4"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        at = _parse_at_lines(result.stdout)
        assert at["total_count"] == "0"
        assert at["parseable_count"] == "0"
        assert at["all_parseable"] == "true"

    def test_sample_data_from_first_file(self):
        """Sample data is emitted from first file (alphabetical)."""
        create_test_video(
            os.path.join(self.temp_dir, "VID_20250505_130334.mp4"),
            DateTimeOriginal="2025:05:05 13:03:34+08:00"
        )
        create_test_video(os.path.join(self.temp_dir, "VID_20250506_140000.mp4"))

        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "report-file-dates.py"),
            self.temp_dir,
            "--file-extensions", ".mp4"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        at = _parse_at_lines(result.stdout)
        assert at["sample_file"] == "VID_20250505_130334.mp4"
        assert at["sample_metadata_date"] == "2025:05:05 13:03:34"
        assert at["sample_metadata_tz"] == "+08:00"
        assert at["sample_filename_date"] == "2025:05:05 13:03:34"
        assert at["sample_filename_pattern"] == "YYYYMMDD_HHMMSS"

    def test_stdout_only_has_at_lines(self):
        """Stdout contains only @@key=value lines."""
        create_test_video(os.path.join(self.temp_dir, "VID_20250505_130334.mp4"))

        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "report-file-dates.py"),
            self.temp_dir,
            "--file-extensions", ".mp4"
        ], capture_output=True, text=True)

        for line in result.stdout.strip().split("\n"):
            if line.strip():
                assert line.startswith("@@"), f"Non-@@ line in stdout: {line}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
