#!/usr/bin/env python3
"""
Scenario-based tests for timezone handling
Tests real-world use cases with specific timezone combinations
"""

import os
import sys
import tempfile
import shutil
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

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


class TestTimezoneScenarios:
    """
    Test real-world timezone scenarios

    These tests capture the actual/expected behavior when:
    - User is in timezone A
    - Video was shot in timezone B
    - How timestamps should appear in different applications
    """

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def create_video_shot_in_timezone(self, filename, shoot_time, shoot_tz_offset):
        """
        Create a video file simulating it was shot at specific time in specific timezone

        Args:
            filename: Name of video file
            shoot_time: datetime object in shooting timezone (e.g., "2025-06-18 07:25:21")
            shoot_tz_offset: Timezone offset string (e.g., "+0800")

        Returns:
            Path to created video
        """
        video_path = os.path.join(self.temp_dir, filename)

        # Create video
        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            video_path
        ], capture_output=True, check=True)

        # Set DateTimeOriginal with shooting timezone
        datetime_original = f"{shoot_time}{shoot_tz_offset}"
        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            f"-DateTimeOriginal={datetime_original}",
            video_path
        ], capture_output=True, check=True)

        return video_path

    def get_keys_creationdate(self, file_path):
        """Get Keys:CreationDate from file"""
        result = subprocess.run([
            "exiftool", "-s", "-Keys:CreationDate", file_path
        ], capture_output=True, text=True, check=True)

        for line in result.stdout.split('\n'):
            if "CreationDate" in line:
                return line.split(':', 1)[1].strip()
        return None

    def test_scenario_viewing_in_japan_shot_in_taiwan(self):
        """
        SCENARIO: User is in Japan (+09:00), video was shot in Taiwan (+08:00)

        Timeline:
        - Shot: 2025-06-18 07:25:21 in Taiwan (+08:00)
        - UTC equivalent: 2025-06-17 23:25:21
        - When viewing in Japan (+09:00): Should display as 2025-06-18 08:25:21

        Expected behavior:
        - DateTimeOriginal: 2025:06:18 07:25:21+08:00 (preserved, source of truth)
        - Keys:CreationDate: 2025:06:18 07:25:21+08:00 (matches DateTimeOriginal)
        - QuickTime CreateDate: 2025:06:17 23:25:21 (UTC)
        - File birth time: Should display as 08:25:21 when viewing in Japan
        """
        # Create video shot at 07:25:21 in Taiwan (+08:00)
        video_path = self.create_video_shot_in_timezone(
            "taiwan_video.mp4",
            "2025:06:18 07:25:21",
            "+08:00"
        )

        # Run fix-media-timestamp (simulating user in Japan, but this should work regardless)
        subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video_path,
            "--apply"
        ], capture_output=True, check=True)

        # Verify DateTimeOriginal is preserved
        fmt._exif_cache.clear()
        exif = fmt.read_exif_data(video_path)
        assert "2025:06:18 07:25:21" in exif.get("DateTimeOriginal", "")
        assert "+08:00" in exif.get("DateTimeOriginal", "")

        # Verify Keys:CreationDate matches DateTimeOriginal
        keys_cd = self.get_keys_creationdate(video_path)
        assert "2025:06:18 07:25:21" in keys_cd
        assert "+08:00" in keys_cd

        # Verify QuickTime CreateDate is in UTC
        qt_create = exif.get("MediaCreateDate", "")
        # Should be 23:25:21 on 2025-06-17 (UTC)
        assert "2025:06:17 23:25:21" in qt_create

    def test_scenario_gopro_footage_different_timezones(self):
        """
        SCENARIO: GoPro footage shot across multiple timezones (e.g., traveling)

        Day 1: Shot in Taiwan (+08:00) at 10:00:00
        Day 2: Shot in Japan (+09:00) at 10:00:00
        Day 3: Shot in Korea (+09:00) at 10:00:00

        Expected: Each video maintains its shooting timezone and appears correctly
        """
        videos = [
            ("taiwan_day1.mp4", "2025:06:18 10:00:00", "+08:00"),
            ("japan_day2.mp4", "2025:06:19 10:00:00", "+09:00"),
            ("korea_day3.mp4", "2025:06:20 10:00:00", "+09:00"),
        ]

        for filename, shoot_time, tz_offset in videos:
            video_path = self.create_video_shot_in_timezone(filename, shoot_time, tz_offset)

            subprocess.run([
                sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
                video_path,
                "--apply"
            ], capture_output=True, check=True)

            # Each should preserve its original timezone
            fmt._exif_cache.clear()
            exif = fmt.read_exif_data(video_path)
            assert shoot_time in exif.get("DateTimeOriginal", "")
            assert tz_offset in exif.get("DateTimeOriginal", "")

    def test_scenario_filename_based_with_timezone(self):
        """
        SCENARIO: Insta360 file with filename timestamp but no EXIF timezone

        Filename: VID_20250618_072521.mp4 (implies 07:25:21 local time)
        User specifies: Shot in Taiwan (+08:00)

        Expected:
        - DateTimeOriginal: 2025:06:18 07:25:21+08:00 (written from filename + TZ)
        - All other fields follow from this
        """
        video_path = os.path.join(self.temp_dir, "VID_20250618_072521.mp4")

        # Create video with no EXIF metadata
        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            video_path
        ], capture_output=True, check=True)

        # Run with timezone flag
        subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video_path,
            "--timezone", "+0800",
            "--apply"
        ], capture_output=True, check=True)

        # Should have written DateTimeOriginal from filename + timezone
        fmt._exif_cache.clear()
        exif = fmt.read_exif_data(video_path)
        assert "2025:06:18 07:25:21" in exif.get("DateTimeOriginal", "")
        assert "+08:00" in exif.get("DateTimeOriginal", "")

    def test_scenario_utc_to_local_conversion(self):
        """
        SCENARIO: File has UTC timestamps, need to specify shooting timezone

        MediaCreateDate: 2025:06:17 23:25:21 (UTC)
        User knows: Shot in Taiwan (+08:00)
        Local time: Should be 2025:06:18 07:25:21

        Expected:
        - DateTimeOriginal: 2025:06:18 07:25:21+08:00 (converted from UTC + TZ)
        """
        video_path = os.path.join(self.temp_dir, "utc_video.mp4")

        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            video_path
        ], capture_output=True, check=True)

        # Set MediaCreateDate as UTC
        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            "-QuickTime:MediaCreateDate=2025:06:17 23:25:21",
            video_path
        ], capture_output=True, check=True)

        # Run with timezone - should convert UTC to local time
        subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video_path,
            "--timezone", "+0800",
            "--apply"
        ], capture_output=True, check=True)

        # Should have created DateTimeOriginal with local time + TZ
        fmt._exif_cache.clear()
        exif = fmt.read_exif_data(video_path)
        dt_original = exif.get("DateTimeOriginal", "")

        # Should show local time (07:25:21 in +08:00, not 23:25:21 UTC)
        assert "2025:06:18 07:25:21" in dt_original
        assert "+08:00" in dt_original

    def test_scenario_negative_timezone(self):
        """
        SCENARIO: Video shot in timezone with negative offset (e.g., New York -05:00)

        Shot: 2025-06-18 14:30:00 in New York (-05:00)
        UTC: 2025-06-18 19:30:00
        Viewing in Japan (+09:00): 2025-06-19 04:30:00
        """
        video_path = self.create_video_shot_in_timezone(
            "ny_video.mp4",
            "2025:06:18 14:30:00",
            "-05:00"
        )

        subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video_path,
            "--apply"
        ], capture_output=True, check=True)

        # Verify negative timezone is preserved
        fmt._exif_cache.clear()
        exif = fmt.read_exif_data(video_path)
        assert "-05:00" in exif.get("DateTimeOriginal", "")

        # Verify UTC conversion is correct
        qt_create = exif.get("MediaCreateDate", "")
        assert "2025:06:18 19:30:00" in qt_create

    def test_scenario_timezone_boundary_date_change(self):
        """
        SCENARIO: Shooting time is late at night, crosses date boundary in UTC

        Shot: 2025-06-18 23:30:00 in Taiwan (+08:00)
        UTC: 2025-06-18 15:30:00 (same day, earlier)

        Shot: 2025-06-18 01:30:00 in Taiwan (+08:00)
        UTC: 2025-06-17 17:30:00 (previous day)
        """
        # Case 1: Late night (same day in UTC)
        video1 = self.create_video_shot_in_timezone(
            "late_night.mp4",
            "2025:06:18 23:30:00",
            "+08:00"
        )

        subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video1,
            "--apply"
        ], capture_output=True, check=True)

        fmt._exif_cache.clear()
        exif1 = fmt.read_exif_data(video1)
        qt1 = exif1.get("MediaCreateDate", "")
        # UTC should be 15:30:00 on same day
        assert "2025:06:18 15:30:00" in qt1

        # Case 2: Early morning (previous day in UTC)
        video2 = self.create_video_shot_in_timezone(
            "early_morning.mp4",
            "2025:06:18 01:30:00",
            "+08:00"
        )

        subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video2,
            "--apply"
        ], capture_output=True, check=True)

        fmt._exif_cache.clear()
        exif2 = fmt.read_exif_data(video2)
        qt2 = exif2.get("MediaCreateDate", "")
        # UTC should be 17:30:00 on previous day
        assert "2025:06:17 17:30:00" in qt2


class TestVideoEditorBehavior:
    """
    Test expected behavior in video editors

    Video editors use:
    - Keys:CreationDate for timeline ordering after import
    - File birth time for "Content Created" on import screen
    """

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def test_timeline_uses_keys_creationdate(self):
        """
        Verify Keys:CreationDate is set for video editor timeline ordering

        Video editors use Keys:CreationDate for "Content Created" after import
        """
        video_path = os.path.join(self.temp_dir, "nle_timeline.mp4")

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

        subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video_path,
            "--apply"
        ], capture_output=True, check=True)

        # Keys:CreationDate should be set
        result = subprocess.run([
            "exiftool", "-s", "-Keys:CreationDate", video_path
        ], capture_output=True, text=True, check=True)

        assert "CreationDate" in result.stdout
        assert "2025:06:18 07:25:21" in result.stdout
        assert "+08:00" in result.stdout


class TestRealWorldWorkflow:
    """
    End-to-end tests simulating real user workflows
    """

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.source_dir = os.path.join(self.temp_dir, "source")
        self.target_dir = os.path.join(self.temp_dir, "target")
        os.makedirs(self.source_dir)
        os.makedirs(self.target_dir)

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        fmt._exif_cache.clear()

    def test_workflow_import_fix_organize(self):
        """
        WORKFLOW: Import GoPro footage → Fix timestamps → Organize by date

        Simulates:
        1. Copying GoPro files from SD card
        2. Running fix-media-timestamp
        3. Running organize-by-date
        4. Verifying video editor will show correct times
        """
        # Create GoPro-style video
        video_path = os.path.join(self.source_dir, "GX010123.MP4")

        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
            video_path
        ], capture_output=True, check=True)

        # Set metadata as if from GoPro
        subprocess.run([
            "exiftool", "-P", "-overwrite_original",
            "-DateTimeOriginal=2025:06:18 10:30:45+08:00",
            "-Make=GoPro",
            "-Model=HERO12 Black",
            video_path
        ], capture_output=True, check=True)

        # Step 1: Fix timestamp
        result = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"),
            video_path,
            "--apply"
        ], capture_output=True, text=True)

        assert result.returncode == 0

        # Verify Keys:CreationDate is set
        fmt._exif_cache.clear()
        exif = fmt.read_exif_data(video_path)
        assert exif.get("CreationDate") is not None

        # Step 2: Organize by date
        subprocess.run([
            "bash", str(SCRIPT_DIR / "organize-by-date.sh"),
            video_path,
            "--target", self.target_dir,
            "--template", "{{YYYY}}-{{MM}}-{{DD}}",
            "--apply"
        ], capture_output=True, check=True)

        # Verify file was moved to correct date folder
        expected_path = os.path.join(self.target_dir, "2025-06-18", "GX010123.MP4")
        assert os.path.exists(expected_path)

        # Verify all metadata is still correct after move
        fmt._exif_cache.clear()
        final_exif = fmt.read_exif_data(expected_path)
        assert "+08:00" in final_exif.get("DateTimeOriginal", "")


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
