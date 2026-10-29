#!/usr/bin/env python3
"""
The metadata client keeps a long-lived exiftool -stay_open child and talks to
it over stdout. A child's stderr that nobody
reads is a deadlock waiting for enough warnings: the pipe fills after ~16 KB,
the child blocks on its next write before it can answer, and the caller waits
forever. A real Korea card wedged at file ~380 this way — every .insv write
emits an "Insta360 trailer" warning. These tests stand in a child that floods
stderr before answering and require the client to still get its answer.
"""

import os
import stat
import sys
import threading
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

FLOOD = 200 * 1024  # well past any pipe buffer


def _executable(path: Path, body: str) -> Path:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _within(seconds, fn):
    """Run fn on a thread; fail the test rather than hang if it never returns."""
    box = {}
    def run():
        try:
            box["value"] = fn()
        except BaseException as e:  # surfaced below
            box["error"] = e
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(seconds)
    assert not t.is_alive(), f"call did not return within {seconds}s — the client is blocked on an undrained pipe"
    if "error" in box:
        raise box["error"]
    return box["value"]


class TestExifToolClient:
    """lib/exiftool.py talking to exiftool -stay_open."""

    def test_exiftool_that_floods_stderr_still_answers(self, tmp_path, monkeypatch, metadata_client):
        _executable(tmp_path / "exiftool", f'''#!/usr/bin/env python3
import sys
sys.stderr.write("Warning: [minor] flood\\n" * ({FLOOD} // 24))
sys.stderr.flush()
n = 0
for line in sys.stdin:
    if line.startswith("-execute"):
        n += 1
        sys.stdout.write("DateTimeOriginal: 2025:06:18 07:25:21\\n")
        sys.stdout.write("{{ready" + line.strip()[len("-execute"):] + "}}\\n")
        sys.stdout.flush()
''')
        monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
        from lib.exiftool import ExifTool
        client = metadata_client(ExifTool())
        result = _within(10, lambda: client.read_tags("x.mp4", ["DateTimeOriginal"]))
        assert result == {"DateTimeOriginal": "2025:06:18 07:25:21"}

    def test_process_is_registered_and_terminated_via_context_manager(self, tmp_path, monkeypatch):
        _executable(tmp_path / "exiftool", '''#!/usr/bin/env python3
import sys
for line in sys.stdin:
    if line.startswith("-execute"):
        sys.stdout.write("DateTimeOriginal: 2025:06:18 07:25:21\\n")
        sys.stdout.write("{ready" + line.strip()[len("-execute"):] + "}\\n")
        sys.stdout.flush()
''')
        monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
        from lib.exiftool import ExifTool, _spawned_pids

        with ExifTool() as client:
            _within(10, lambda: client.read_tags("x.mp4", ["DateTimeOriginal"]))
            pid = client._process.pid
            assert pid in _spawned_pids

        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
