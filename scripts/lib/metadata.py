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
    """Resolve path to the jetlag-metadata binary, or None if not found.

    ``JETLAG_METADATA_BINARY`` overrides the search: a path selects that binary,
    and an empty value forces the Python fallback. Which backend is in use
    changes the process tree a cancel has to tear down, so tests need to pick
    one rather than inherit whichever the machine happens to have built.
    """
    override = os.environ.get("JETLAG_METADATA_BINARY")
    if override is not None:
        return override or None

    tools_dir = os.path.join(os.path.dirname(__file__), "..", "tools")
    candidate = os.path.join(tools_dir, "jetlag-metadata")
    if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
        return os.path.abspath(candidate)
    import shutil
    if shutil.which("jetlag-metadata"):
        return "jetlag-metadata"
    return None


# pids of every jetlag-metadata child this process has spawned, so a test
# session can confirm none of them are still running at session end.
_spawned_pids: list[int] = []


class _SwiftBackend:
    """Talks to jetlag-metadata CLI via JSON-over-stdin/stdout."""

    def __init__(self, binary_path: str):
        self._binary = binary_path
        self._process = None
        self._lock = threading.Lock()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def _ensure_running(self):
        if self._process is not None and self._process.poll() is None:
            return
        # stderr is inherited, not piped: a pipe nobody reads fills after ~16 KB
        # and blocks the writer, and this client only ever reads stdout lines.
        # jetlag-metadata writes nothing to stderr in normal operation; anything it
        # does write reaches the pipeline's own stderr, which the caller drains.
        self._process = subprocess.Popen(
            [self._binary],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
        )
        _spawned_pids.append(self._process.pid)

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
            response = json.loads(response_line.decode())
            # exiftool's warnings ride along on the response so they are never left
            # in a pipe; they are diagnostics, not data.
            response.pop("warnings", None)
            response.pop("_warnings", None)
            return response

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
        """Close jetlag-metadata's stdin so it shuts its own exiftool down.

        The lock is taken opportunistically: a signal handler runs on the same
        thread that may already hold it inside :meth:`_call`, so blocking here
        would deadlock the shutdown and leave the whole chain running.
        """
        acquired = self._lock.acquire(blocking=False)
        try:
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
        finally:
            if acquired:
                self._lock.release()


def _create_service():
    binary = _find_jetlag_metadata()
    if binary:
        return _SwiftBackend(binary)
    from lib.exiftool import ExifTool
    return ExifTool()


metadata_service = _create_service()
atexit.register(metadata_service.close)
