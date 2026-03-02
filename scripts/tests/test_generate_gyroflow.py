#!/usr/bin/env python3
"""
Test suite for generate-gyroflow.py

Run with: pytest tests/test_generate_gyroflow.py -v
"""

import importlib.util
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


def _load_generate_gyroflow():
    """Load generate-gyroflow.py as a module (filename has a hyphen)."""
    spec = importlib.util.spec_from_file_location(
        "generate_gyroflow", SCRIPT_DIR / "generate-gyroflow.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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

    def test_missing_binary_skips_gracefully(self):
        """Missing Gyroflow binary should skip gracefully, not crash the pipeline."""
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
                # Restrict PATH to tmpdir (fake ffprobe) + essentials only,
                # so shutil.which("gyroflow") won't find a real install
                env["PATH"] = f"{tmpdir}:/usr/bin:/bin"

                result = subprocess.run(
                    [sys.executable, str(SCRIPT_DIR / "generate-gyroflow.py"),
                     str(video), "--preset", get_test_preset(), "--apply"],
                    capture_output=True, text=True, env=env, cwd=SCRIPT_DIR,
                )

                assert result.returncode == 0, "Missing binary should not crash — exit 0 and skip"
                assert "not found" in result.stderr.lower()
                assert "@@error=" in result.stdout
                assert "@@action=skipped" in result.stdout

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


class TestBinaryResolution:
    """Tests for resolve_gyroflow_binary — bundled binary takes priority over
    configured path and system PATH, so the app can ship self-contained."""

    def test_bundled_binary_preferred_over_configured(self):
        """A bundled gyroflow in scripts/tools/ should be used even when a
        configured path also exists — bundled tools are the preferred source
        for the macOS app bundle."""
        mod = _load_generate_gyroflow()
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_scripts = Path(tmpdir) / "scripts"
            fake_tools = fake_scripts / "tools"
            fake_tools.mkdir(parents=True)
            bundled = fake_tools / "gyroflow"
            bundled.write_text("#!/bin/bash\necho bundled")
            bundled.chmod(0o755)

            configured = Path(tmpdir) / "configured" / "gyroflow"
            configured.parent.mkdir()
            configured.write_text("#!/bin/bash\necho configured")
            configured.chmod(0o755)

            original_dir = mod.SCRIPT_DIR
            try:
                mod.SCRIPT_DIR = fake_scripts
                result = mod.resolve_gyroflow_binary(str(configured))
                assert result == str(bundled), (
                    f"Bundled binary should be preferred, got {result}"
                )
            finally:
                mod.SCRIPT_DIR = original_dir

    def test_configured_path_used_when_no_bundled(self):
        """When no bundled binary exists, the configured path from
        media-profiles.yaml should be used."""
        mod = _load_generate_gyroflow()
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_scripts = Path(tmpdir) / "scripts"
            fake_tools = fake_scripts / "tools"
            fake_tools.mkdir(parents=True)

            configured = Path(tmpdir) / "configured" / "gyroflow"
            configured.parent.mkdir()
            configured.write_text("#!/bin/bash\necho configured")
            configured.chmod(0o755)

            original_dir = mod.SCRIPT_DIR
            try:
                mod.SCRIPT_DIR = fake_scripts
                result = mod.resolve_gyroflow_binary(str(configured))
                assert result == str(configured), (
                    f"Configured path should be used when no bundle, got {result}"
                )
            finally:
                mod.SCRIPT_DIR = original_dir

    def test_returns_none_when_nothing_found(self):
        """When no bundled, configured, or PATH binary exists, returns None
        so the caller can skip gracefully."""
        mod = _load_generate_gyroflow()
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_scripts = Path(tmpdir) / "scripts"
            fake_tools = fake_scripts / "tools"
            fake_tools.mkdir(parents=True)

            original_dir = mod.SCRIPT_DIR
            original_path = os.environ.get("PATH", "")
            try:
                mod.SCRIPT_DIR = fake_scripts
                os.environ["PATH"] = "/nonexistent"
                result = mod.resolve_gyroflow_binary("/no/such/binary")
                assert result is None, "Should return None when nothing found"
            finally:
                mod.SCRIPT_DIR = original_dir
                os.environ["PATH"] = original_path


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
