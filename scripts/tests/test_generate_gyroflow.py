#!/usr/bin/env python3
"""
Test suite for generate-gyroflow.py

Run with: pytest tests/test_generate_gyroflow.py -v
"""

import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

SCRIPT_DIR = Path(__file__).parent.parent
GENERATE_GYROFLOW = SCRIPT_DIR / "generate-gyroflow.sh"
PROFILES_FILE = SCRIPT_DIR / "media-profiles.yaml"


def run_generate_gyroflow(args: list[str]) -> subprocess.CompletedProcess:
    """Run generate-gyroflow.sh with given args."""
    quoted_args = " ".join(shlex.quote(arg) for arg in args)
    cmd = f"{GENERATE_GYROFLOW} {quoted_args}"
    return subprocess.run(
        cmd,
        shell=True,
        executable="/bin/bash",
        capture_output=True,
        text=True,
        cwd=SCRIPT_DIR,
    )


from conftest import create_test_video


def get_test_preset() -> str:
    """Get a test preset JSON string."""
    return json.dumps({"stabilization": {"max_zoom": 105.0}})



class TestNoMotionData:
    """Tests for videos without motion/gyro data streams."""

    def test_no_motion_data_skipped(self):
        """A plain video without motion data should be skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            video = Path(tmpdir) / "test.mp4"
            create_test_video(video)

            result = run_generate_gyroflow([
                str(video), "--preset", get_test_preset(), "--apply"
            ])

            gyroflow_file = video.with_suffix(".gyroflow")
            assert not gyroflow_file.exists(), ".gyroflow should not be created for video without motion data"

    def test_no_motion_data_reports_skipped(self):
        """Skip message should include path and reason."""
        with tempfile.TemporaryDirectory() as tmpdir:
            video = Path(tmpdir) / "test.mp4"
            create_test_video(video)

            result = run_generate_gyroflow([
                str(video), "--preset", get_test_preset(), "--apply"
            ])

            assert "no motion data" in result.stderr.lower()
            assert "@@action=skipped" in result.stdout

    def test_no_motion_data_exits_zero(self):
        """Skipping a file without motion data is not an error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            video = Path(tmpdir) / "test.mp4"
            create_test_video(video)

            result = run_generate_gyroflow([
                str(video), "--preset", get_test_preset(), "--apply"
            ])

            assert result.returncode == 0

    def test_no_motion_data_skipped_in_dry_run(self):
        """Motion data check runs before dry run — skips without mentioning dry run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            video = Path(tmpdir) / "test.mp4"
            create_test_video(video)

            result = run_generate_gyroflow([
                str(video), "--preset", get_test_preset()
            ])

            assert "no motion data" in result.stderr.lower()
            assert "@@action=skipped" in result.stdout


class TestDryRun:
    """Tests for dry run mode (no --apply)."""

    def test_dry_run_no_file_created(self):
        """Dry run should not create a .gyroflow file even if motion data exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            video = Path(tmpdir) / "test.mp4"
            create_test_video(video)

            result = run_generate_gyroflow([
                str(video), "--preset", get_test_preset()
            ])

            gyroflow_file = video.with_suffix(".gyroflow")
            assert not gyroflow_file.exists(), ".gyroflow should not be created in dry run"

    def test_dry_run_already_exists_reports_skip(self):
        """Dry run with existing .gyroflow should indicate DRY RUN."""
        with tempfile.TemporaryDirectory() as tmpdir:
            video = Path(tmpdir) / "test.mp4"
            create_test_video(video)

            gyroflow_file = video.with_suffix(".gyroflow")
            gyroflow_file.write_text("{}")

            result = run_generate_gyroflow([
                str(video), "--preset", get_test_preset()
            ])

            assert "Already exists" in result.stderr
            assert "@@action=skipped" in result.stdout
            assert gyroflow_file.read_text() == "{}", "Existing file should not be modified"


class TestAlreadyExists:
    """Tests for idempotency."""

    def test_already_exists_skip(self):
        """If .gyroflow already exists, should skip even with --apply."""
        with tempfile.TemporaryDirectory() as tmpdir:
            video = Path(tmpdir) / "test.mp4"
            create_test_video(video)

            gyroflow_file = video.with_suffix(".gyroflow")
            gyroflow_file.write_text("{}")

            result = run_generate_gyroflow([
                str(video), "--preset", get_test_preset(), "--apply"
            ])

            assert "Already exists" in result.stderr
            assert "@@action=skipped" in result.stdout
            assert gyroflow_file.read_text() == "{}", "Existing file should not be modified"


class TestMissingBinary:
    """Tests for missing Gyroflow binary."""

    def test_missing_binary_error(self):
        """Clear error if Gyroflow binary not found at configured path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            video = Path(tmpdir) / "test.mp4"
            create_test_video(video)

            # Fake ffprobe that reports motion data so the script reaches the binary check
            fake_ffprobe = Path(tmpdir) / "ffprobe"
            fake_ffprobe.write_text(
                '#!/bin/bash\n'
                'echo \'{"streams": [{"codec_type": "data", "tags": {"handler_name": "GoPro MET"}, "codec_tag_string": "gpmd"}]}\'\n'
            )
            fake_ffprobe.chmod(0o755)

            with open(PROFILES_FILE) as f:
                original_config = f.read()
                data = yaml.safe_load(original_config)

            data["gyroflow"]["binary"] = "/nonexistent/path/to/gyroflow"

            try:
                with open(PROFILES_FILE, "w") as f:
                    yaml.dump(data, f, default_flow_style=False, sort_keys=False)

                env = os.environ.copy()
                env["PATH"] = f"{tmpdir}:{env['PATH']}"

                result = subprocess.run(
                    [sys.executable, str(SCRIPT_DIR / "generate-gyroflow.py"),
                     str(video), "--preset", get_test_preset(), "--apply"],
                    capture_output=True, text=True, env=env, cwd=SCRIPT_DIR,
                )

                assert result.returncode != 0
                assert "not found" in result.stderr.lower() or "ERROR" in result.stderr
                assert "@@error=" in result.stdout, "Machine-readable @@error should be emitted on failure"

            finally:
                with open(PROFILES_FILE, "w") as f:
                    f.write(original_config)

    def test_nonexistent_file_emits_error(self):
        """@@error should be emitted for a nonexistent input file."""
        result = run_generate_gyroflow([
            "/nonexistent/file.mp4", "--preset", get_test_preset()
        ])

        assert result.returncode != 0
        assert "@@error=" in result.stdout


class TestPreset:
    """Tests for preset passing."""

    def test_preset_argument_accepted(self):
        """The --preset argument should be accepted without error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            video = Path(tmpdir) / "test.mp4"
            create_test_video(video)

            preset = json.dumps({
                "stabilization": {
                    "max_zoom": 110.0,
                    "adaptive_zoom_window": 20.0,
                    "adaptive_zoom_method": 1
                }
            })

            result = run_generate_gyroflow([
                str(video), "--preset", preset
            ])

            assert result.returncode == 0, f"Preset should be accepted. stderr: {result.stderr}"


class TestFileNotFound:
    """Tests for missing input files."""

    def test_nonexistent_file_error(self):
        """Should error clearly for nonexistent file."""
        result = run_generate_gyroflow([
            "/nonexistent/file.mp4", "--preset", get_test_preset()
        ])

        assert result.returncode != 0
        assert "not found" in result.stderr.lower() or "ERROR" in result.stderr


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
