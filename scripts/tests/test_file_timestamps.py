#!/usr/bin/env python3
"""
Tests for macOS file-system timestamp operations (birth time via SetFile/stat -f).

All tests in this file require macOS and are skipped on other platforms.
"""

import os
import sys
import tempfile
import shutil
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# Import hyphenated module name
import importlib.util
spec = importlib.util.spec_from_file_location(
    "fix_media_timestamp",
    str(Path(__file__).parent.parent / "fix-media-timestamp.py")
)
fmt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fmt)

if sys.platform == "darwin":
    from lib.file_timestamps import (
        get_file_system_timestamps,
        set_file_system_timestamps,
        check_file_system_timestamps_need_update,
        get_expected_file_system_time,
    )

SCRIPT_DIR = Path(__file__).parent.parent


@pytest.mark.skipif(sys.platform != "darwin", reason="requires macOS — birth time operations")
class TestFileTimestamps:
    """Tests for macOS file-system timestamp read/write operations"""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_video = os.path.join(self.temp_dir, "test.mp4")

        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            self.test_video
        ], capture_output=True, check=True)

        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            "-DateTimeOriginal=2025:06:18 07:25:21+08:00",
            self.test_video
        ], capture_output=True, check=True)

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def test_get_file_system_timestamps(self):
        """Test reading file system timestamps"""
        timestamps = get_file_system_timestamps(self.test_video)

        assert "birth" in timestamps
        assert "modify" in timestamps
        assert len(timestamps["birth"]) > 0
        assert len(timestamps["modify"]) > 0

    def test_set_file_system_timestamps_birth_only(self):
        """Test that only birth time is set, not modification time"""
        timestamp_str = "2025:06:18 07:25:21"

        original_mtime = os.stat(self.test_video).st_mtime

        success = set_file_system_timestamps(self.test_video, timestamp_str)

        assert success is True

        new_stat = os.stat(self.test_video)
        new_birthtime = new_stat.st_birthtime

        expected_dt = datetime.strptime(timestamp_str, '%Y:%m:%d %H:%M:%S')

        birthtime_dt = datetime.fromtimestamp(new_birthtime)
        diff = abs((birthtime_dt - expected_dt).total_seconds())
        assert diff < 2

        new_mtime = new_stat.st_mtime
        if new_mtime != original_mtime:
            mtime_dt = datetime.fromtimestamp(new_mtime)
            now = datetime.now()
            assert abs((mtime_dt - now).total_seconds()) < 10

    def test_birthtime_tolerance_within_60_seconds(self):
        """Test that birthtime differences <= 60 seconds don't trigger update"""
        dt = datetime(2025, 6, 18, 7, 25, 21, tzinfo=timezone(timedelta(hours=8)))

        subprocess.run([
            "SetFile", "-d", "06/18/2025 07:24:22", self.test_video
        ], capture_output=True, check=True)

        needs_update = check_file_system_timestamps_need_update(
            self.test_video, dt, preserve_wallclock=True
        )

        assert needs_update is False, "59 second difference should NOT trigger update"

    def test_birthtime_tolerance_exceeds_60_seconds(self):
        """Test that birthtime differences > 60 seconds trigger update"""
        dt = datetime(2025, 6, 18, 7, 25, 21, tzinfo=timezone(timedelta(hours=8)))

        subprocess.run([
            "SetFile", "-d", "06/18/2025 07:24:20", self.test_video
        ], capture_output=True, check=True)

        needs_update = check_file_system_timestamps_need_update(
            self.test_video, dt, preserve_wallclock=True
        )

        assert needs_update is True, "61 second difference should trigger update"

    def test_preserve_wallclock_affects_file_timestamps(self):
        """Test that preserve_wallclock parameter is passed through"""
        dt = datetime(2025, 6, 18, 7, 25, 21, tzinfo=timezone(timedelta(hours=8)))

        subprocess.run([
            "SetFile", "-d", "06/18/2025 07:25:21", self.test_video
        ], capture_output=True, check=True)

        changes = fmt.determine_needed_changes(self.test_video, dt, preserve_wallclock=True)
        assert changes["file_timestamps"] is False

    def test_get_expected_file_system_time_display_mode(self):
        """Test file system time calculation in display mode (default)"""
        dt = datetime(2025, 6, 18, 7, 25, 21, tzinfo=timezone(timedelta(hours=8)))

        result = get_expected_file_system_time(dt, preserve_wallclock=False)

        expected_local = dt.astimezone().strftime('%Y:%m:%d %H:%M:%S')
        assert result == expected_local

    def test_get_expected_file_system_time_wallclock_mode(self):
        """Test file system time calculation in wallclock mode"""
        dt = datetime(2025, 6, 18, 7, 25, 21, tzinfo=timezone(timedelta(hours=8)))

        result = get_expected_file_system_time(dt, preserve_wallclock=True)

        assert result == "2025:06:18 07:25:21"

    def test_apply_mode_changes_birth_time(self):
        """Test that apply mode updates birth time"""
        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            self.test_video, "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        assert "(DRY RUN)" not in result.stdout

        new_stat = os.stat(self.test_video)
        assert new_stat.st_birthtime != 0

    def test_birth_time_only_no_mtime(self):
        """Test that only birth time is set, not modification time"""
        original_mtime = os.stat(self.test_video).st_mtime

        subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            self.test_video, "--apply"
        ], capture_output=True, check=True)

        new_mtime = os.stat(self.test_video).st_mtime
        assert new_mtime >= original_mtime

    def test_import_screen_uses_birth_time(self):
        """Verify that file birth time is set correctly for video editor import screen"""
        subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            self.test_video, "--apply"
        ], capture_output=True, check=True)

        birth_time = os.stat(self.test_video).st_birthtime
        assert birth_time > 0

        birth_dt = datetime.fromtimestamp(birth_time)
        assert birth_dt.year == 2025
        assert birth_dt.month == 6


@pytest.mark.skipif(sys.platform != "darwin", reason="requires macOS — birth time operations")
class TestBirthTimeCalculation:
    """
    Regression test: Birth time calculation must be accurate

    Bug: Birth time was off by 1 hour when converting from Keys:CreationDate
    Example: Keys:CreationDate = 07:15:30+08:00
    - Expected birth (UTC): 23:15:30
    - Was getting:          22:15:30 (1 hour wrong)
    """

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def _create_test_video(self, path: str, datetime_with_tz: str) -> None:
        """Create a test video with specific DateTimeOriginal"""
        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            path
        ], capture_output=True, check=True)

        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            f"-DateTimeOriginal={datetime_with_tz}",
            path
        ], capture_output=True, check=True)

    def _get_birth_time_local(self, path: str) -> str:
        """Get file birth time in local timezone"""
        result = subprocess.run(
            ["stat", "-f", "%SB", "-t", "%Y:%m:%d %H:%M:%S", path],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()

    def test_birth_time_regular_mode(self):
        """
        Birth time in regular mode should match UTC converted to current system timezone.

        File shot at 07:15:30 in Taiwan (+08:00) -> UTC 2025-06-17 23:15:30.
        Expected birth time = that UTC instant in the system's local timezone
        (accounting for DST on the video's date, not today's date).
        """
        video_path = os.path.join(self.temp_dir, "test_taiwan.mp4")
        self._create_test_video(video_path, "2025:06:18 07:15:30+08:00")

        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video_path,
            "--timezone", "+0800",
            "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0, f"Script failed:\n{result.stderr}"

        birth_local = self._get_birth_time_local(video_path)
        actual_time = birth_local.split()[1]

        shoot_utc = datetime(2025, 6, 17, 23, 15, 30, tzinfo=timezone.utc)
        expected_local = shoot_utc.astimezone().strftime("%H:%M:%S")

        assert actual_time == expected_local, (
            f"Birth time incorrect in regular mode:\n"
            f"  Expected: {expected_local}\n"
            f"  Actual:   {actual_time}\n"
            f"  Full:     {birth_local}"
        )

    def test_birth_time_idempotency_regular(self):
        """Running script twice in regular mode should not change birth time second time"""
        video_path = os.path.join(self.temp_dir, "test_idempotent.mp4")
        self._create_test_video(video_path, "2025:06:18 07:15:30+08:00")

        subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video_path,
            "--timezone", "+0800",
            "--apply"
        ], capture_output=True, check=True)

        birth_after_first = self._get_birth_time_local(video_path)

        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video_path,
            "--timezone", "+0800"
        ], capture_output=True, text=True, check=True)

        assert "No change" in result.stdout or "no change" in result.stdout.lower(), (
            f"Second run should detect no changes:\n{result.stdout}"
        )

        birth_after_second = self._get_birth_time_local(video_path)

        assert birth_after_first == birth_after_second, (
            f"Birth time should not change on second run:\n"
            f"  After first:  {birth_after_first}\n"
            f"  After second: {birth_after_second}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
