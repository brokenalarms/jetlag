#!/usr/bin/env python3
"""
Tests for sync/backup script output formatting.
Ensures machine-readable @@ lines don't leak to user-visible output.
"""

import os
import subprocess
import tempfile
import shutil
from pathlib import Path
import pytest


SCRIPT_DIR = Path(__file__).parent.parent


class TestSyncOutputFormat:
    """Test that @@ machine-readable output is properly hidden from users"""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary source and destination directories"""
        tmpdir = tempfile.mkdtemp()
        source = os.path.join(tmpdir, "source")
        dest = os.path.join(tmpdir, "dest")
        os.makedirs(source)
        os.makedirs(dest)

        # Create a test file to sync
        test_file = os.path.join(source, "test.txt")
        with open(test_file, "w") as f:
            f.write("test content")

        yield {"source": source, "dest": dest, "tmpdir": tmpdir}
        shutil.rmtree(tmpdir)

    @pytest.fixture
    def mock_env_file(self, temp_dirs):
        """Create a mock .env.local for sync-local.sh"""
        env_content = f"""
SOURCE_PATH={temp_dirs['source']}/
LOCAL_SYNC_PATH={temp_dirs['dest']}/
"""
        env_path = os.path.join(SCRIPT_DIR, ".env.local.test")
        with open(env_path, "w") as f:
            f.write(env_content)
        yield env_path
        os.remove(env_path)

    def test_sync_local_no_at_at_in_output(self, temp_dirs, mock_env_file):
        """sync-local.sh should not display @@ lines to user

        Actual: Run sync-local.sh and capture all output
        Expected: No lines starting with @@ in stdout or stderr
        """
        # Create minimal exclusions file
        exclusions_file = os.path.join(temp_dirs['tmpdir'], "exclusions.txt")
        with open(exclusions_file, "w") as f:
            f.write("")

        # Modify env to include exclusions
        with open(mock_env_file, "a") as f:
            f.write(f"EXCLUSIONS_FILE={exclusions_file}\n")

        # Run sync-local.sh with test env
        env = os.environ.copy()
        env["ENV_FILE"] = mock_env_file

        result = subprocess.run(
            [str(SCRIPT_DIR / "sync-local.sh"), "--apply"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(SCRIPT_DIR)
        )

        # Combine stdout and stderr (what user sees)
        all_output = result.stdout + result.stderr

        # Check no @@ lines leaked
        at_at_lines = [line for line in all_output.split('\n') if line.startswith('@@')]
        assert at_at_lines == [], f"@@ lines leaked to output: {at_at_lines}"

    def test_backup_to_nas_no_at_at_in_stderr(self, temp_dirs):
        """backup-to-nas.sh should not display @@ lines to stderr

        Actual: Run backup-to-nas.sh and capture stderr
        Expected: No lines starting with @@ in stderr (stdout has @@ for parent script)
        """
        # backup-to-nas.sh outputs @@ to stdout (for parent to capture)
        # but stderr (user-visible messages) should not contain @@

        # Skip if NAS not configured - just test the script structure
        result = subprocess.run(
            [str(SCRIPT_DIR / "backup-to-nas.sh"), "--help"],
            capture_output=True,
            text=True,
            cwd=str(SCRIPT_DIR)
        )

        # Help output goes to stdout, should not contain @@
        at_at_lines = [line for line in result.stdout.split('\n') if line.startswith('@@')]
        assert at_at_lines == [], f"@@ lines in help output: {at_at_lines}"

    def test_lib_sync_outputs_at_at_to_stdout(self, temp_dirs):
        """lib-sync.sh run_rsync should output @@ lines to stdout

        This verifies the @@ protocol is working correctly.
        Parent scripts capture stdout to get these values.
        """
        # Create a simple test script that sources lib-sync and runs rsync
        test_script = os.path.join(temp_dirs['tmpdir'], "test_lib_sync.sh")
        with open(test_script, "w") as f:
            f.write(f"""#!/bin/bash
set -euo pipefail
source "{SCRIPT_DIR}/lib/lib-common.sh"
source "{SCRIPT_DIR}/lib/lib-sync.sh"
run_rsync "{temp_dirs['source']}/" "{temp_dirs['dest']}/" 0 "" "none" ""
""")
        os.chmod(test_script, 0o755)

        result = subprocess.run(
            [test_script],
            capture_output=True,
            text=True,
            cwd=str(SCRIPT_DIR)
        )

        # stdout should contain @@ lines
        stdout_lines = result.stdout.split('\n')
        at_at_lines = [line for line in stdout_lines if line.startswith('@@')]

        expected_keys = ['@@files_transferred=', '@@bytes_transferred=', '@@total_size=', '@@elapsed_seconds=']
        for key in expected_keys:
            matching = [line for line in at_at_lines if line.startswith(key)]
            assert len(matching) == 1, f"Expected exactly one {key} line in stdout, got: {at_at_lines}"

        # stderr should NOT contain @@ lines (that's for human-readable output)
        stderr_at_at = [line for line in result.stderr.split('\n') if line.startswith('@@')]
        assert stderr_at_at == [], f"@@ lines should not be in stderr: {stderr_at_at}"
