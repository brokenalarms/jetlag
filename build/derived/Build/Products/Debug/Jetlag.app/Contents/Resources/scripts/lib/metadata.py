"""
Metadata service — single entry point for all EXIF/metadata operations.

All scripts should import from here instead of lib.exiftool. The backend
can be swapped without touching callers.

When jetlag-metadata CLI is available, uses the Swift binary (persistent
JSON-over-stdin/stdout protocol). Falls back to the Python ExifTool
wrapper otherwise.

Usage:
    from lib.metadata import metadata_service
    tags = metadata_service.read_tags(path, ["DateTimeOriginal", "Make"])
    metadata_service.write_tags(path, ["-Make=GoPro"])
"""

import atexit
import json
import os
import subprocess
import threading


def _find_jetlag_metadata():
    """Resolve path to the jetlag-metadata binary, or None if not found."""
    tools_dir = os.path.join(os.path.dirname(__file__), "..", "tools")
    candidate = os.path.join(tools_dir, "jetlag-metadata")
    if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
        return os.path.abspath(candidate)
    import shutil
    if shutil.which("jetlag-metadata"):
        return "jetlag-metadata"
    return None


class _SwiftBackend:
    """Talks to jetlag-metadata CLI via JSON-over-stdin/stdout."""

    def __init__(self, binary_path: str):
        self._binary = binary_path
        self._process = None
        self._lock = threading.Lock()

    def _ensure_running(self):
        if self._process is not None and self._process.poll() is None:
            return
        self._process = subprocess.Popen(
            [self._binary],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def _call(self, request: dict) -> dict:
        with self._lock:
            self._ensure_running()
            assert self._process is not None

            line = json.dumps(request, separators=(",", ":")) + "\n"
            self._process.stdin.write(line.encode())
            self._process.stdin.flush()

            response_line = self._process.stdout.readline()
            if not response_line:
                return {}
            return json.loads(response_line.decode())

    def read_tags(self, file_path, tags, extra_args=None):
        fast = bool(extra_args and "-fast2" in extra_args)
        return self._call({
            "op": "read",
            "file": str(file_path),
            "tags": list(tags),
            "fast": fast,
        })

    def write_tags(self, file_path, tag_args):
        tags = {}
        for arg in tag_args:
            key, _, val = arg.lstrip("-").partition("=")
            tags[key] = val
        result = self._call({
            "op": "write",
            "file": str(file_path),
            "tags": tags,
        })
        return result.get("updated", False)

    def close(self):
        with self._lock:
            if self._process is None or self._process.poll() is not None:
                self._process = None
                return
            try:
                self._process.stdin.close()
                self._process.wait(timeout=5)
            except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                self._process.kill()
                self._process.wait()
            self._process = None


def _create_service():
    binary = _find_jetlag_metadata()
    if binary:
        return _SwiftBackend(binary)
    from lib.exiftool import ExifTool
    return ExifTool()


metadata_service = _create_service()
atexit.register(metadata_service.close)
