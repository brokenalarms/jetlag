#!/usr/bin/env python3
"""
Every metadata client keeps a long-lived child (jetlag-metadata, and under it
exiftool -stay_open) and talks to it over stdout. A child's stderr that nobody
reads is a deadlock waiting for enough warnings: the pipe fills after ~16 KB,
the child blocks on its next write before it can answer, and the caller waits
forever. A real Korea card wedged at file ~380 this way — every .insv write
emits an "Insta360 trailer" warning. These tests stand in a child that floods
stderr before answering and require every client to still get its answer.
"""

import os
import shutil
import stat
import subprocess
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


class TestSwiftBackendClient:
    """lib/metadata.py talking to jetlag-metadata."""

    def test_backend_that_floods_stderr_still_answers(self, tmp_path):
        fake = _executable(tmp_path / "jetlag-metadata", f'''#!/usr/bin/env python3
import sys
sys.stderr.write("w" * {FLOOD})
sys.stderr.flush()
for line in sys.stdin:
    sys.stdout.write('{{"DateTimeOriginal":"2025:06:18 07:25:21"}}\\n')
    sys.stdout.flush()
''')
        from lib.metadata import _SwiftBackend
        client = _SwiftBackend(str(fake))
        try:
            result = _within(10, lambda: client.read_tags("x.mp4", ["DateTimeOriginal"]))
        finally:
            client.close()
        assert result == {"DateTimeOriginal": "2025:06:18 07:25:21"}


class TestExifToolFallbackClient:
    """lib/exiftool.py talking to exiftool -stay_open directly."""

    def test_exiftool_that_floods_stderr_still_answers(self, tmp_path, monkeypatch):
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
        client = ExifTool()
        try:
            result = _within(10, lambda: client.read_tags("x.mp4", ["DateTimeOriginal"]))
        finally:
            client.close()
        assert result == {"DateTimeOriginal": "2025:06:18 07:25:21"}


METADATA_BINARY = SCRIPTS_DIR / "tools" / "jetlag-metadata"


@pytest.mark.skipif(
    not (METADATA_BINARY.is_file() and os.access(METADATA_BINARY, os.X_OK)),
    reason="jetlag-metadata binary not built — run scripts/tools/build-jetlag-metadata.sh",
)
class TestJetlagMetadataDrainsExifTool:
    """The real jetlag-metadata binary against an exiftool that floods stderr.

    The binary resolves `exiftool` as a sibling of itself, so a copy of it in a
    temp dir next to the fake exiftool exercises exactly the code path the app
    uses — the one that wedged the Korea run.
    """

    def test_real_binary_survives_a_flooding_exiftool(self, tmp_path):
        binary = tmp_path / "jetlag-metadata"
        shutil.copy2(METADATA_BINARY, binary)
        _executable(tmp_path / "exiftool", f'''#!/usr/bin/env python3
import sys
for line in sys.stdin:
    if line.strip() == "False":
        break
    if line.startswith("-execute"):
        sys.stderr.write("Warning: [minor] Insta360 trailer at offset 0x6b4a5f2\\n" * ({FLOOD} // 56))
        sys.stderr.flush()
        sys.stdout.write("    1 image files updated\\n")
        sys.stdout.write("{{ready" + line.strip()[len("-execute"):] + "}}\\n")
        sys.stdout.flush()
''')
        from lib.metadata import _SwiftBackend
        client = _SwiftBackend(str(binary))
        try:
            # Several requests: the pipe must never accumulate across them.
            for _ in range(3):
                updated = _within(15, lambda: client.write_tags("x.mp4", ["-DateTimeOriginal=2025:06:18 07:25:21"]))
                assert updated is True
        finally:
            client.close()

    def test_warnings_are_surfaced_not_swallowed(self, tmp_path):
        binary = tmp_path / "jetlag-metadata"
        shutil.copy2(METADATA_BINARY, binary)
        _executable(tmp_path / "exiftool", '''#!/usr/bin/env python3
import sys
for line in sys.stdin:
    if line.strip() == "False":
        break
    if line.startswith("-execute"):
        sys.stderr.write("Warning: [minor] Insta360 trailer at offset 0x6b4a5f2\\n")
        sys.stderr.flush()
        sys.stdout.write("    1 image files updated\\n")
        sys.stdout.write("{ready" + line.strip()[len("-execute"):] + "}\\n")
        sys.stdout.flush()
''')
        import json
        proc = subprocess.Popen([str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None)
        try:
            proc.stdin.write(b'{"op":"write","file":"x.mp4","tags":{"DateTimeOriginal":"2025:06:18 07:25:21"}}\n')
            proc.stdin.flush()
            response = json.loads(_within(15, lambda: proc.stdout.readline()).decode())
        finally:
            proc.stdin.close()
            proc.wait(timeout=5)
        assert response["updated"] is True
        assert "Insta360 trailer" in response.get("warnings", ""), response
