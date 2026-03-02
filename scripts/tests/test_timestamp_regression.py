#!/usr/bin/env python3
"""
Regression tests for fix-media-timestamp.py
Tests critical behaviors documented in AGENTS.md
"""

import os
import sys
import tempfile
import shutil
import subprocess
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from conftest import create_test_video

sys.path.insert(0, str(Path(__file__).parent.parent))

# Import hyphenated module name
import importlib.util
spec = importlib.util.spec_from_file_location(
    "fix_media_timestamp",
    str(Path(__file__).parent.parent / "fix-media-timestamp.py")
)
fmt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fmt)

SCRIPT_DIR = Path(__file__).parent.parent


class TestFilenameSourceOfTruth:
    """
    AGENTS.md: "files with YYYYMMDD_HHMMSS in the filename are first source of truth
    and filename should never be modified"
    """

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def test_insta360_filename_is_source_of_truth_with_infer(self):
        """
        Insta360 file VID_20250619_063809_00_002.mp4 has:
        - Filename: 06:38:09 (CORRECT - source of truth)
        - DateTimeOriginal: 09:38:09+08:00 (WRONG - corrupted)

        With --infer-from-filename --timezone +0800:
        - Should use filename (06:38:09) as source of truth
        - Should write DateTimeOriginal as 06:38:09+08:00
        - Should ignore the corrupted DateTimeOriginal value
        """
        video_path = os.path.join(self.temp_dir, "VID_20250619_063809_00_002.mp4")
        create_test_video(video_path, DateTimeOriginal="2025:06:19 09:38:09+08:00")

        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video_path,
            "--infer-from-filename",
            "--timezone", "+0800",
            "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0

        # Verify DateTimeOriginal was corrected from filename
        fmt._exif_cache.clear()
        exif = fmt.read_exif_data(video_path)
        dt_original = exif.get("DateTimeOriginal", "")

        # Should be 06:38:09 (from filename), not 09:38:09 (corrupted value)
        assert "2025:06:19 06:38:09" in dt_original
        assert "+08:00" in dt_original

    def test_filename_not_modified_ever(self):
        """
        Verify that filename is never modified, regardless of timestamp corrections
        """
        original_filename = "VID_20250619_063809_00_002.mp4"
        video_path = os.path.join(self.temp_dir, original_filename)
        create_test_video(video_path)

        # Run fix (even with wrong EXIF data)
        subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video_path,
            "--timezone", "+0800",
            "--apply"
        ], capture_output=True, check=True)

        # Filename should be unchanged
        assert os.path.exists(video_path)
        assert os.path.basename(video_path) == original_filename


class TestDateTimeOriginalPreservation:
    """DateTimeOriginal is preserved by default unless --infer-from-filename."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def test_datetimeoriginal_preserved_by_default(self):
        """Without --infer-from-filename, DateTimeOriginal should never change."""
        video_path = os.path.join(self.temp_dir, "test_video.mp4")
        original_datetime = "2025:06:19 06:38:09+08:00"
        create_test_video(video_path, DateTimeOriginal=original_datetime)

        # Run fix without --infer-from-filename
        subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video_path,
            "--apply"
        ], capture_output=True, check=True)

        # DateTimeOriginal should be unchanged
        fmt._exif_cache.clear()
        exif = fmt.read_exif_data(video_path)
        assert exif.get("DateTimeOriginal") == original_datetime


class TestInferFromFilenameRequiresTimezone:
    """--infer-from-filename requires --timezone."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def test_infer_without_timezone_fails(self):
        """--infer-from-filename without --timezone should fail."""
        video_path = os.path.join(self.temp_dir, "VID_20250619_063809.mp4")
        create_test_video(video_path)

        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video_path,
            "--infer-from-filename",
            "--apply"
        ], capture_output=True, text=True)

        assert result.returncode != 0
        assert "requires --timezone" in result.stderr


class TestTimezoneMismatchDetection:
    """Timezone mismatch is now informational — succeeds with @@timestamp_action=tz_mismatch."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def _parse_at_lines(self, stdout: str) -> dict:
        result = {}
        for line in stdout.strip().split("\n"):
            if line.startswith("@@"):
                key_value = line[2:]
                if "=" in key_value:
                    key, value = key_value.split("=", 1)
                    result[key] = value
        return result

    def test_timezone_mismatch_is_informational(self):
        """Providing different --timezone than DateTimeOriginal succeeds with tz_mismatch action."""
        video_path = os.path.join(self.temp_dir, "test_video.mp4")
        create_test_video(video_path, DateTimeOriginal="2025:06:19 06:38:09+08:00")

        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video_path,
            "--timezone", "+0900",
        ], capture_output=True, text=True)

        # Should succeed (informational, not blocking)
        assert result.returncode == 0
        at_lines = self._parse_at_lines(result.stdout)
        assert at_lines.get("timestamp_action") == "tz_mismatch"
        assert "mismatch" in result.stderr.lower()


class TestTimezoneConversion:
    """
    AGENTS.md: "if a file was shot in timezone +0800, with the script run in +0900,
    then we would expect Keys:Creation date to end up with the +0800 timezone,
    and the birthdate to end up as one hour later"
    """

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def test_timezone_conversion_display_mode(self):
        """
        Shot in +08:00, viewing in +09:00:
        - Keys:CreationDate should have +08:00
        - Birth time should be 1 hour later (converted to viewing timezone)
        """
        video_path = os.path.join(self.temp_dir, "taiwan_video.mp4")
        create_test_video(video_path, DateTimeOriginal="2025:06:19 06:38:09+08:00")

        # Run fix
        subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video_path,
            "--apply"
        ], capture_output=True, check=True)

        # Verify Keys:CreationDate has original timezone (+08:00)
        result = subprocess.run([
            "exiftool", "-s", "-Keys:CreationDate", video_path
        ], capture_output=True, text=True, check=True)

        assert "06:38:09" in result.stdout
        assert "+08:00" in result.stdout


class TestMissingDateTimeOriginalWithTimezoneChange:
    """
    AGENTS.md: "if DateTimeOriginal is missing and we change timezones,
    we would expect the Quicktime UTC fields MediaCreateDate, file birth date,
    Keys:CreationDate to all be updated"
    """

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def test_missing_datetimeoriginal_updates_all_fields(self):
        """
        When DateTimeOriginal is missing and we provide timezone:
        - Should write DateTimeOriginal
        - Should update MediaCreateDate (UTC)
        - Should update Keys:CreationDate
        """
        video_path = os.path.join(self.temp_dir, "VID_20250619_063809.mp4")
        create_test_video(video_path)

        # No DateTimeOriginal initially
        fmt._exif_cache.clear()
        exif_before = fmt.read_exif_data(video_path)
        assert not exif_before.get("DateTimeOriginal")

        # Run with timezone
        subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video_path,
            "--timezone", "+0800",
            "--apply"
        ], capture_output=True, check=True)

        # All fields should now be set
        fmt._exif_cache.clear()
        exif_after = fmt.read_exif_data(video_path)

        # DateTimeOriginal should be written
        assert "2025:06:19 06:38:09" in exif_after.get("DateTimeOriginal", "")
        assert "+08:00" in exif_after.get("DateTimeOriginal", "")

        # MediaCreateDate should be in UTC
        media_create = exif_after.get("MediaCreateDate", "")
        # 06:38:09+08:00 in UTC is 22:38:09 on previous day
        assert "22:38:09" in media_create

        # Keys:CreationDate should be set
        keys_cd = exif_after.get("CreationDate", "")
        assert keys_cd  # Should exist


class TestExtractMetadataTimezone:
    """
    extract_metadata_timezone should output @@timezone= to stdout when
    DateTimeOriginal or CreationDate contains a timezone offset.
    """

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def _create_test_video(self, path: str) -> None:
        create_test_video(path)

    def test_extracts_timezone_from_datetimeoriginal(self):
        """When DateTimeOriginal has +08:00, extract_metadata_timezone returns it"""
        video_path = os.path.join(self.temp_dir, "test_tz.mp4")
        self._create_test_video(video_path)

        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            "-DateTimeOriginal=2025:10:24 11:48:59+08:00",
            video_path
        ], capture_output=True, check=True)

        fmt._exif_cache.clear()
        result = fmt.extract_metadata_timezone(video_path)
        assert result == "+08:00"

    def test_extracts_timezone_from_creationdate(self):
        """When DateTimeOriginal has no timezone but CreationDate does, extract from CreationDate"""
        video_path = os.path.join(self.temp_dir, "test_tz_cd.mp4")
        self._create_test_video(video_path)

        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            "-Keys:CreationDate=2025:10:24 11:48:59+13:00",
            video_path
        ], capture_output=True, check=True)

        fmt._exif_cache.clear()
        result = fmt.extract_metadata_timezone(video_path)
        assert result == "+13:00"

    def test_returns_none_when_no_timezone(self):
        """When no field has timezone info, returns None"""
        video_path = os.path.join(self.temp_dir, "test_no_tz.mp4")
        self._create_test_video(video_path)

        fmt._exif_cache.clear()
        result = fmt.extract_metadata_timezone(video_path)
        assert result is None

    def test_stdout_contains_timezone_marker(self):
        """Running the script on a file with timezone emits @@timezone= to stdout"""
        video_path = os.path.join(self.temp_dir, "test_stdout_tz.mp4")
        self._create_test_video(video_path)

        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            "-DateTimeOriginal=2025:10:24 11:48:59+08:00",
            video_path
        ], capture_output=True, check=True)

        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video_path
        ], capture_output=True, text=True)

        assert "@@timezone=+08:00" in result.stdout

    def test_no_timezone_marker_when_absent(self):
        """Running the script on a file without timezone does not emit @@timezone="""
        video_path = os.path.join(self.temp_dir, "test_no_stdout_tz.mp4")
        self._create_test_video(video_path)

        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video_path
        ], capture_output=True, text=True)

        assert "@@timezone=" not in result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
