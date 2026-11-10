"""
How the pipeline settles each file's time: --timezone and the embedded zone,
--infer-from-filename and --time-offset. The pure pre-flight decision is in
test_pipeline_preflight.py; these hold the whole run's effect on the files.
"""



from conftest import create_test_video as _create_video_raw
from pipeline_helpers import create_test_video, get_exif_field, run_pipeline


class TestTimezoneHandling:
    """Tests for timezone parameter handling."""

    def test_timezone_affects_local_time_calculation(self, temp_workspace, test_profile):
        """Different timezones produce different local times."""
        source = temp_workspace["source"]
        target = temp_workspace["target"]

        # MediaCreateDate 01:00 UTC
        # In +0900: 10:00 local
        # In +0200: 03:00 local
        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:10:05 01:00:00")

        run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "+0900", "--group", "Test", "--apply"],
        )

        moved = list(target.rglob("*.mp4"))[0]
        dto = get_exif_field(moved, "DateTimeOriginal")
        assert "10:00:00" in dto, f"Should be 10:00 in +0900, got: {dto}"

    def test_timezone_format_validation(self, temp_workspace, test_profile):
        """Invalid timezone format is rejected."""
        source = temp_workspace["source"]
        video = source / "test.mp4"
        create_test_video(video)

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source), "--timezone", "JST", "--group", "Test"],
        )

        assert result.returncode != 0
        assert "ERROR" in result.output or "+HHMM" in result.output

    def test_unknown_zone_name_is_rejected(self, temp_workspace, test_profile):
        """A zone name that is not in the database is rejected."""
        source = temp_workspace["source"]
        create_test_video(source / "test.mp4")

        result = run_pipeline(
            ["--profile", test_profile, "--source", str(source),
             "--timezone", "Pacific/Atlantis", "--group", "Test"],
        )

        assert result.returncode != 0
        assert "unknown timezone" in result.output.lower()

    def test_zone_name_resolves_per_file_across_a_dst_changeover(self, temp_workspace, test_profile):
        """One run, one zone, two offsets — NZ left daylight time on 2025-04-06.

        Both files carry the same UTC instant on either side of the changeover,
        so a single frozen offset would give them the same local hour.
        """
        source = temp_workspace["source"]
        target = temp_workspace["target"]
        create_test_video(source / "summer.mp4", media_create_date="2025:03:15 01:00:00")
        create_test_video(source / "winter.mp4", media_create_date="2025:07:15 01:00:00")

        run_pipeline(
            ["--profile", test_profile, "--source", str(source),
             "--timezone", "Pacific/Auckland", "--group", "Test", "--apply"],
        )

        moved = {p.name: p for p in target.rglob("*.mp4")}
        summer = get_exif_field(moved["summer.mp4"], "DateTimeOriginal")
        winter = get_exif_field(moved["winter.mp4"], "DateTimeOriginal")

        assert "+13:00" in summer, f"March is NZDT, got: {summer}"
        assert "+12:00" in winter, f"July is NZST, got: {winter}"
        assert "14:00:00" in summer, f"01:00 UTC is 14:00 NZDT, got: {summer}"
        assert "13:00:00" in winter, f"01:00 UTC is 13:00 NZST, got: {winter}"


class TestInferFromFilename:
    """Tests for --infer-from-filename pass-through to fix-timestamp."""

    def test_infer_from_filename_passes_through(self, temp_workspace, test_profile):
        """Pipeline passes --infer-from-filename to fix-timestamp, correcting DateTimeOriginal from filename.

        Actual: DateTimeOriginal on output file matches filename timestamp + timezone
        Expected: filename timestamp used as source of truth
        """
        source = temp_workspace["source"]
        target = temp_workspace["target"]
        video = source / "VID_20250619_063809_00_002.mp4"
        _create_video_raw(
            video,
            MediaCreateDate="2025:06:18 22:38:09",
            CreateDate="2025:06:18 22:38:09",
            DateTimeOriginal="2025:06:19 09:38:09+08:00",
        )

        run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0800",
            "--group", "Test",
            "--infer-from-filename",
            "--apply",
        ])

        moved = list(target.rglob("*.mp4"))[0]
        dto = get_exif_field(moved, "DateTimeOriginal")
        assert "06:38:09" in dto, f"Should use filename time 06:38:09, got: {dto}"
        assert "+08:00" in dto, f"Should have +08:00 timezone, got: {dto}"

    def test_infer_from_filename_requires_timezone(self, temp_workspace, test_profile):
        """--infer-from-filename without --timezone is rejected by pipeline."""
        source = temp_workspace["source"]
        video = source / "VID_20250619_063809.mp4"
        create_test_video(video)

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--group", "Test",
            "--infer-from-filename",
        ])

        assert result.returncode != 0


class TestTimeOffset:
    """Tests for --time-offset pass-through to fix-timestamp."""

    def test_time_offset_passes_through(self, temp_workspace, test_profile):
        """Pipeline passes --time-offset to fix-timestamp, shifting timestamps.

        Actual: DateTimeOriginal on output file is shifted by offset seconds
        Expected: 3600s offset shifts 01:00:00 UTC → 02:00:00 UTC → 11:00:00+09:00
        """
        source = temp_workspace["source"]
        target = temp_workspace["target"]
        video = source / "test.mp4"
        create_test_video(video, media_create_date="2025:10:05 01:00:00")

        run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--timezone", "+0900",
            "--group", "Test",
            "--time-offset", "3600",
            "--apply",
        ])

        moved = list(target.rglob("*.mp4"))[0]
        dto = get_exif_field(moved, "DateTimeOriginal")
        # 01:00 UTC + 3600s = 02:00 UTC → 11:00 in +0900
        assert "11:00:00" in dto, f"Expected 11:00:00 (shifted by 1h), got: {dto}"

    def test_time_offset_requires_timezone(self, temp_workspace, test_profile):
        """--time-offset without --timezone is rejected by pipeline."""
        source = temp_workspace["source"]
        video = source / "test.mp4"
        create_test_video(video)

        result = run_pipeline([
            "--profile", test_profile,
            "--source", str(source),
            "--group", "Test",
            "--time-offset", "3600",
        ])

        assert result.returncode != 0
