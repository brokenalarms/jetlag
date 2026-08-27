#!/usr/bin/env python3
"""
conftest.py tracks every exiftool -stay_open / jetlag-metadata child spawned
by lib.exiftool / lib.metadata (lib/exiftool.py's and lib/metadata.py's
_spawned_pids registries) and fails the session at pytest_sessionfinish if
any of them are still alive — the mechanism that catches a leaked -stay_open
process. These tests exercise that mechanism directly rather than via a full
nested pytest run.
"""

import stat
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(Path(__file__).parent))

from conftest import _leaked_metadata_pids
import lib.exiftool as exiftool_module


def _executable(path: Path, body: str) -> Path:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_a_live_registered_process_is_reported_as_leaked(tmp_path):
    fake = _executable(tmp_path / "exiftool", '''#!/usr/bin/env python3
import time
time.sleep(30)
''')
    proc = subprocess.Popen([str(fake)])
    exiftool_module._spawned_pids.append(proc.pid)
    try:
        leaked = _leaked_metadata_pids()
        assert any(f"pid {proc.pid} " in entry for entry in leaked)
    finally:
        proc.kill()
        proc.wait()
        exiftool_module._spawned_pids.remove(proc.pid)


def test_a_terminated_registered_process_is_not_reported(tmp_path):
    fake = _executable(tmp_path / "exiftool", '''#!/usr/bin/env python3
import time
time.sleep(30)
''')
    proc = subprocess.Popen([str(fake)])
    proc.kill()
    proc.wait()
    exiftool_module._spawned_pids.append(proc.pid)
    try:
        leaked = _leaked_metadata_pids()
        assert not any(f"pid {proc.pid} " in entry for entry in leaked)
    finally:
        exiftool_module._spawned_pids.remove(proc.pid)


def test_module_level_metadata_service_is_registered_when_used():
    """The shared metadata_service singleton (used by conftest's
    create_test_video/create_test_photo and every production script) records
    its own pid the same way a test-constructed client does, so the session
    close fixture's teardown is exactly what the leak check verifies."""
    from conftest import exiftool
    import lib.metadata as metadata_module

    exiftool._ensure_running()
    pid = exiftool._process.pid

    assert pid in exiftool_module._spawned_pids or pid in metadata_module._spawned_pids
