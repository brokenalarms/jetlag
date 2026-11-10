#!/usr/bin/env python3
"""
conftest.py tracks every exiftool -stay_open child spawned by lib.exiftool
(its _spawned_pids registry) and fails the session at pytest_sessionfinish if
any of them are still alive — the mechanism that catches a leaked -stay_open
process. These tests exercise that mechanism directly rather than via a full
nested pytest run.
"""

import stat
import subprocess
import time
from pathlib import Path

from conftest import _leaked_metadata_pids
import lib.exiftool as exiftool_module

SCRIPTS_DIR = Path(__file__).parent.parent


def _executable(path: Path, body: str) -> Path:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _wait_until_execed(pid: int, name: str, timeout: float = 5.0) -> None:
    """Popen returns once the child is forked, which can be before it execs:
    until then ps shows the parent's (pytest's) command line. Wait for the
    child's own command so the leak check sees what a real leak would show."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        cmd = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True
        ).stdout
        if name in cmd:
            return
        time.sleep(0.02)
    raise AssertionError(f"pid {pid} never showed {name!r} in ps")


def test_a_live_registered_process_is_reported_as_leaked(tmp_path):
    fake = _executable(tmp_path / "exiftool", '''#!/usr/bin/env python3
import time
time.sleep(30)
''')
    proc = subprocess.Popen([str(fake)])
    _wait_until_execed(proc.pid, "exiftool")
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


def test_module_level_exiftool_is_registered_when_used():
    """The shared exiftool singleton (used by conftest's
    create_test_video/create_test_photo and every production script) records
    its own pid the same way a test-constructed client does, so the session
    close fixture's teardown is exactly what the leak check verifies."""
    from conftest import exiftool

    exiftool._ensure_running()
    pid = exiftool._process.pid

    assert pid in exiftool_module._spawned_pids
