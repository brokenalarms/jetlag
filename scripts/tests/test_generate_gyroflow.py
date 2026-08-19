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
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

import pytest
import yaml

SCRIPT_DIR = Path(__file__).parent.parent
GENERATE_GYROFLOW = SCRIPT_DIR / "generate-gyroflow.sh"
PROFILES_FILE = SCRIPT_DIR / "media-profiles.yaml"
DOWNLOAD_GYROFLOW = SCRIPT_DIR / "tools" / "download-gyroflow.sh"


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

            # Point the script at a modified copy of the profiles file via the
            # JETLAG_PROFILES_FILE override — the shared repo file is never
            # touched, so this test is safe under parallel workers.
            with open(PROFILES_FILE) as f:
                data = yaml.safe_load(f)
            data["gyroflow"]["binary"] = "/nonexistent/path/to/gyroflow"
            profiles_copy = Path(tmpdir) / "media-profiles.yaml"
            with open(profiles_copy, "w") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)

            env = os.environ.copy()
            env["JETLAG_PROFILES_FILE"] = str(profiles_copy)
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

    def test_nonexistent_file_emits_error(self):
        """@@error should be emitted for a nonexistent input file."""
        result = run_generate_gyroflow([
            "/nonexistent/file.mp4", "--preset", get_test_preset()
        ])

        assert result.returncode != 0
        assert "@@error=" in result.stdout


class TestBinaryResolution:
    """Tests for resolve_gyroflow_binary. Gyroflow is not bundled inside the
    signed Jetlag app: a bare CLI binary copied out of Gyroflow.app has an
    invalid signature and is missing its mdk/Qt frameworks. Resolution instead
    walks real installs in a fixed order — /Applications, the Jetlag-managed
    Application Support tools dir, $PATH, then the configured path."""

    @staticmethod
    def _make_app(root: Path) -> Path:
        """Build a synthetic Gyroflow.app under root and return its CLI binary."""
        binary = root / "Gyroflow.app" / "Contents" / "MacOS" / "gyroflow"
        binary.parent.mkdir(parents=True)
        binary.write_text("#!/bin/bash\necho gyroflow")
        binary.chmod(0o755)
        return binary

    @staticmethod
    def _make_path_binary(root: Path) -> Path:
        binary = root / "gyroflow"
        binary.write_text("#!/bin/bash\necho gyroflow")
        binary.chmod(0o755)
        return binary

    @contextmanager
    def _isolated(self, applications: Path, tools: Path, path_dir: Optional[Path] = None):
        """Point resolution at synthetic directories instead of the real machine."""
        saved = {k: os.environ.get(k) for k in ("JETLAG_APPLICATIONS_DIR", "JETLAG_TOOLS_DIR", "PATH")}
        try:
            os.environ["JETLAG_APPLICATIONS_DIR"] = str(applications)
            os.environ["JETLAG_TOOLS_DIR"] = str(tools)
            os.environ["PATH"] = str(path_dir) if path_dir else "/nonexistent"
            yield
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_applications_install_wins_over_every_other_source(self):
        """A user's own /Applications/Gyroflow.app is the first choice, ahead of
        a Jetlag-installed copy, a $PATH binary, and a configured path."""
        mod = _load_generate_gyroflow()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            applications = root / "Applications"
            tools = root / "tools"
            path_dir = root / "bin"
            for d in (applications, tools, path_dir):
                d.mkdir()
            expected = self._make_app(applications)
            self._make_app(tools)
            self._make_path_binary(path_dir)
            configured = self._make_path_binary(root)

            with self._isolated(applications, tools, path_dir):
                assert mod.resolve_gyroflow_binary(str(configured)) == str(expected)

    def test_jetlag_tools_install_used_when_applications_empty(self):
        """The copy download-gyroflow.sh installs into Application Support is
        used when the user has no /Applications install."""
        mod = _load_generate_gyroflow()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            applications = root / "Applications"
            tools = root / "tools"
            path_dir = root / "bin"
            for d in (applications, tools, path_dir):
                d.mkdir()
            expected = self._make_app(tools)
            self._make_path_binary(path_dir)
            configured = self._make_path_binary(root)

            with self._isolated(applications, tools, path_dir):
                assert mod.resolve_gyroflow_binary(str(configured)) == str(expected)

    def test_path_binary_used_when_no_app_bundle_installed(self):
        """A gyroflow on $PATH (e.g. a Homebrew install) is used when neither
        app-bundle location has one."""
        mod = _load_generate_gyroflow()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            applications = root / "Applications"
            tools = root / "tools"
            path_dir = root / "bin"
            for d in (applications, tools, path_dir):
                d.mkdir()
            expected = self._make_path_binary(path_dir)
            configured = self._make_path_binary(root)

            with self._isolated(applications, tools, path_dir):
                assert mod.resolve_gyroflow_binary(str(configured)) == str(expected)

    def test_configured_path_is_the_last_resort(self):
        """The media-profiles.yaml binary path is used only when no install is
        found in either app location or on $PATH."""
        mod = _load_generate_gyroflow()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            applications = root / "Applications"
            tools = root / "tools"
            for d in (applications, tools):
                d.mkdir()
            configured = self._make_path_binary(root)

            with self._isolated(applications, tools):
                assert mod.resolve_gyroflow_binary(str(configured)) == str(configured)

    def test_returns_none_when_nothing_found(self):
        """When no install exists anywhere, returns None so the caller can skip
        gracefully instead of crashing the pipeline."""
        mod = _load_generate_gyroflow()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            applications = root / "Applications"
            tools = root / "tools"
            for d in (applications, tools):
                d.mkdir()

            with self._isolated(applications, tools):
                assert mod.resolve_gyroflow_binary("/no/such/binary") is None


class TestDownloadGyroflowCheck:
    """Tests for scripts/tools/download-gyroflow.sh --check, the presence probe
    the app polls to decide whether to show gyroflow features at all. It reports
    machine-readable presence data and must never download or write anything."""

    @staticmethod
    def _parse(stdout: str) -> dict[str, str]:
        return dict(
            line[2:].split("=", 1)
            for line in stdout.splitlines()
            if line.startswith("@@") and "=" in line
        )

    @staticmethod
    def _make_app(root: Path) -> Path:
        binary = root / "Gyroflow.app" / "Contents" / "MacOS" / "gyroflow"
        binary.parent.mkdir(parents=True)
        binary.write_text("#!/bin/bash\necho gyroflow")
        binary.chmod(0o755)
        return binary

    def _run_check(self, applications: Path, tools: Path, path_dir: Optional[Path] = None,
                   extra_args: Optional[list[str]] = None) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["JETLAG_APPLICATIONS_DIR"] = str(applications)
        env["JETLAG_TOOLS_DIR"] = str(tools)
        env["PATH"] = f"{path_dir}:/usr/bin:/bin" if path_dir else "/usr/bin:/bin"
        return subprocess.run(
            [str(DOWNLOAD_GYROFLOW), "--check"] + (extra_args or []),
            capture_output=True, text=True, env=env,
        )

    def test_check_reports_absence_without_downloading(self):
        """With no install anywhere, --check reports @@present=false and leaves
        the tools directory untouched — the app must be able to poll cheaply
        without triggering a multi-hundred-MB download."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            applications = root / "Applications"
            tools = root / "tools"
            for d in (applications, tools):
                d.mkdir()

            result = self._run_check(applications, tools)

            assert result.returncode == 0, result.stderr
            assert self._parse(result.stdout)["present"] == "false"
            assert list(tools.iterdir()) == [], "--check must not install anything"

    def test_check_reports_existing_applications_install(self):
        """An existing /Applications install is reported, not re-downloaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            applications = root / "Applications"
            tools = root / "tools"
            for d in (applications, tools):
                d.mkdir()
            expected = self._make_app(applications)

            fields = self._parse(self._run_check(applications, tools).stdout)

            assert fields["present"] == "true"
            assert fields["path"] == str(expected)
            assert fields["source"] == "applications"

    def test_check_reports_jetlag_managed_install(self):
        """A copy previously installed into Application Support is reported with
        its own source, so the app can tell it apart from a user install."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            applications = root / "Applications"
            tools = root / "tools"
            for d in (applications, tools):
                d.mkdir()
            expected = self._make_app(tools)

            fields = self._parse(self._run_check(applications, tools).stdout)

            assert fields["present"] == "true"
            assert fields["path"] == str(expected)
            assert fields["source"] == "jetlag-tools"

    def test_check_reports_path_install(self):
        """A gyroflow on $PATH counts as present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            applications = root / "Applications"
            tools = root / "tools"
            path_dir = root / "bin"
            for d in (applications, tools, path_dir):
                d.mkdir()
            expected = path_dir / "gyroflow"
            expected.write_text("#!/bin/bash\necho gyroflow")
            expected.chmod(0o755)

            fields = self._parse(self._run_check(applications, tools, path_dir).stdout)

            assert fields["present"] == "true"
            assert fields["path"] == str(expected)
            assert fields["source"] == "path"

    def test_check_reports_configured_path_last(self):
        """An explicitly configured binary is the final fallback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            applications = root / "Applications"
            tools = root / "tools"
            for d in (applications, tools):
                d.mkdir()
            configured = root / "gyroflow"
            configured.write_text("#!/bin/bash\necho gyroflow")
            configured.chmod(0o755)

            fields = self._parse(self._run_check(
                applications, tools, extra_args=["--configured", str(configured)]
            ).stdout)

            assert fields["present"] == "true"
            assert fields["path"] == str(configured)
            assert fields["source"] == "configured"

    def test_install_target_is_never_inside_the_app_bundle(self):
        """The installer writes to Application Support, never into the signed
        Jetlag.app — writing there would break its code signature."""
        body = DOWNLOAD_GYROFLOW.read_text()
        assert "Application Support/Jetlag/tools" in body
        assert "Contents/Resources" not in body


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
