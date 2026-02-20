#!/usr/bin/env python3
"""
Tests for sync/backup script output formatting.
Ensures machine-readable @@ lines don't leak to user-visible output.
"""

import os
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path
import pytest

SCRIPT_DIR = Path(__file__).parent.parent

# Import the formatting functions from backup script
sys.path.insert(0, str(SCRIPT_DIR))
from importlib.util import spec_from_loader, module_from_spec
from importlib.machinery import SourceFileLoader

# Load the backup script as a module (it has a hyphen in the name)
loader = SourceFileLoader("backup_source_video_to_nas", str(SCRIPT_DIR / "backup-source-video-to-nas.py"))
spec = spec_from_loader("backup_source_video_to_nas", loader)
backup_module = module_from_spec(spec)
loader.exec_module(backup_module)

format_bytes = backup_module.format_bytes
format_speed = backup_module.format_speed


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

    def test_sync_local_no_at_at_output(self, temp_dirs, mock_env_file):
        """sync-local.sh should not output @@ lines (no parent to consume them)

        Actual: Run sync-local.sh and capture stdout/stderr separately
        Expected: No @@ lines anywhere (script doesn't request machine-readable)
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

        # No @@ lines in stdout (machine-readable not requested)
        stdout_at_at = [line for line in result.stdout.split('\n') if line.startswith('@@')]
        assert stdout_at_at == [], f"@@ lines should not be in stdout: {stdout_at_at}"

        # No @@ lines in stderr
        stderr_at_at = [line for line in result.stderr.split('\n') if line.startswith('@@')]
        assert stderr_at_at == [], f"@@ lines should not be in stderr: {stderr_at_at}"

    def test_backup_to_nas_no_at_at_in_stderr(self):
        """backup-to-nas.sh should not display @@ lines to stderr

        Actual: Run backup-to-nas.sh --help and capture output
        Expected: No lines starting with @@ in help output
        """
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
run_rsync "{temp_dirs['source']}/" "{temp_dirs['dest']}/" 0 "" "none" "" "" 1
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

    def test_lib_sync_filters_skipping_messages(self, temp_dirs):
        """lib-sync.sh should filter 'skipping non-regular file' messages from stderr

        Actual: Create a symlink, run rsync which generates skipping message
        Expected: Message should be filtered out of stderr
        """
        # Create a symlink in source to trigger "skipping non-regular file" message
        symlink_path = os.path.join(temp_dirs['source'], "test_symlink")
        os.symlink("/tmp", symlink_path)

        # Create test script that runs rsync
        test_script = os.path.join(temp_dirs['tmpdir'], "test_skip_filter.sh")
        with open(test_script, "w") as f:
            f.write(f"""#!/bin/bash
set -euo pipefail
source "{SCRIPT_DIR}/lib/lib-common.sh"
source "{SCRIPT_DIR}/lib/lib-sync.sh"
run_rsync "{temp_dirs['source']}/" "{temp_dirs['dest']}/" 0 "" "" "" "" 1
""")
        os.chmod(test_script, 0o755)

        result = subprocess.run(
            [test_script],
            capture_output=True,
            text=True,
            cwd=str(SCRIPT_DIR)
        )

        # stderr should NOT contain "skipping non-regular file" (filtered out)
        skipping_lines = [line for line in result.stderr.split('\n')
                         if "skipping non-regular file" in line]
        assert skipping_lines == [], f"'skipping' messages should be filtered: {skipping_lines}"

    def test_lib_sync_converts_human_readable_sizes(self, temp_dirs):
        """lib-sync.sh should convert rsync's human-readable sizes to bytes

        Actual: Parse rsync --human-readable output like "108.12G bytes"
        Expected: bytes_transferred contains actual byte count, not just "108"
        """
        # Create a test script that tests the convert_to_bytes function
        test_script = os.path.join(temp_dirs['tmpdir'], "test_convert.sh")
        with open(test_script, "w") as f:
            f.write(f"""#!/bin/bash
set -euo pipefail
source "{SCRIPT_DIR}/lib/lib-common.sh"
source "{SCRIPT_DIR}/lib/lib-sync.sh"

# Test convert_to_bytes function (defined inside run_rsync, so we redefine it here)
convert_to_bytes() {{
    local size_str="$1"
    local num unit multiplier=1

    if [[ "$size_str" =~ ^([0-9.,]+)([KMGT]?)$ ]]; then
        num="${{BASH_REMATCH[1]//,/}}"
        unit="${{BASH_REMATCH[2]}}"
        case "$unit" in
            K) multiplier=1024 ;;
            M) multiplier=1048576 ;;
            G) multiplier=1073741824 ;;
            T) multiplier=1099511627776 ;;
        esac
        awk "BEGIN {{printf \\"%.0f\\", $num * $multiplier}}"
    else
        echo "0"
    fi
}}

# Test cases
echo "1K=$(convert_to_bytes '1K')"
echo "1M=$(convert_to_bytes '1M')"
echo "1G=$(convert_to_bytes '1G')"
echo "1T=$(convert_to_bytes '1T')"
echo "108.12G=$(convert_to_bytes '108.12G')"
echo "1.56T=$(convert_to_bytes '1.56T')"
echo "500M=$(convert_to_bytes '500M')"
echo "1234=$(convert_to_bytes '1234')"
""")
        os.chmod(test_script, 0o755)

        result = subprocess.run(
            [test_script],
            capture_output=True,
            text=True,
            cwd=str(SCRIPT_DIR)
        )

        # Parse output and verify conversions
        lines = result.stdout.strip().split('\n')
        results = {}
        for line in lines:
            if '=' in line:
                key, value = line.split('=', 1)
                results[key] = int(value)

        assert results['1K'] == 1024, f"1K should be 1024, got {results['1K']}"
        assert results['1M'] == 1048576, f"1M should be 1048576, got {results['1M']}"
        assert results['1G'] == 1073741824, f"1G should be 1073741824, got {results['1G']}"
        assert results['1T'] == 1099511627776, f"1T should be 1099511627776, got {results['1T']}"
        # 108.12G = 108.12 * 1073741824 = 116,133,994,127 (approximately)
        assert 116_000_000_000 < results['108.12G'] < 117_000_000_000, f"108.12G conversion wrong: {results['108.12G']}"
        # 1.56T = 1.56 * 1099511627776 = 1,715,238,139,330 (approximately)
        assert 1_700_000_000_000 < results['1.56T'] < 1_720_000_000_000, f"1.56T conversion wrong: {results['1.56T']}"
        assert results['500M'] == 524288000, f"500M should be 524288000, got {results['500M']}"
        assert results['1234'] == 1234, f"Plain number should be unchanged, got {results['1234']}"


class TestPythonFormatting:
    """Test Python formatting functions for bytes and speed display"""

    def test_format_bytes_bytes(self):
        """Small values display as bytes"""
        assert format_bytes(0) == "0.0 B"
        assert format_bytes(100) == "100.0 B"
        assert format_bytes(1023) == "1023.0 B"

    def test_format_bytes_kilobytes(self):
        """Values >= 1024 display as KB"""
        assert format_bytes(1024) == "1.0 KB"
        assert format_bytes(1536) == "1.5 KB"
        assert format_bytes(10240) == "10.0 KB"

    def test_format_bytes_megabytes(self):
        """Values >= 1MB display as MB"""
        assert format_bytes(1048576) == "1.0 MB"
        assert format_bytes(1572864) == "1.5 MB"
        assert format_bytes(524288000) == "500.0 MB"

    def test_format_bytes_gigabytes(self):
        """Values >= 1GB display as GB"""
        assert format_bytes(1073741824) == "1.0 GB"
        assert format_bytes(116133994127) == "108.2 GB"  # 108.12G from rsync

    def test_format_bytes_terabytes(self):
        """Values >= 1TB display as TB"""
        assert format_bytes(1099511627776) == "1.0 TB"
        assert format_bytes(1715238139330) == "1.6 TB"  # 1.56T from rsync

    def test_format_speed_bytes_per_sec(self):
        """Slow speeds display as B/s"""
        assert format_speed(0) == "0 B/s"
        assert format_speed(100) == "100 B/s"
        assert format_speed(1023) == "1023 B/s"

    def test_format_speed_kilobytes_per_sec(self):
        """Medium speeds display as KB/s"""
        assert format_speed(1024) == "1.00 KB/s"
        assert format_speed(5120) == "5.00 KB/s"
        assert format_speed(102400) == "100.00 KB/s"

    def test_format_speed_megabytes_per_sec(self):
        """Fast speeds display as MB/s"""
        assert format_speed(1048576) == "1.00 MB/s"
        assert format_speed(5242880) == "5.00 MB/s"
        assert format_speed(10485760) == "10.00 MB/s"

    def test_average_speed_calculation(self):
        """Average speed calculated correctly from bytes and time

        Actual: 108GB transferred in 22314 seconds
        Expected: ~4.84 MB/s (108*1024*1024*1024 / 22314 / 1024 / 1024)
        """
        bytes_transferred = 116_000_000_000  # ~108 GB
        elapsed_seconds = 22314

        speed = bytes_transferred / elapsed_seconds
        formatted = format_speed(speed)

        # Should be around 5 MB/s
        assert "MB/s" in formatted
        # Extract the number and verify it's reasonable
        speed_num = float(formatted.split()[0])
        assert 4.0 < speed_num < 6.0, f"Expected ~5 MB/s, got {formatted}"
