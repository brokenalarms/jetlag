"""
Persistent jetlag-metadata subprocess wrapper.

jetlag-metadata is a Swift CLI that wraps ExifTool behind a JSON-in/JSON-out
interface. This module keeps a single persistent process alive, sending
one-line JSON requests via stdin and reading one-line JSON responses from
stdout — eliminating per-invocation overhead.

Usage:
    from lib.metadata import metadata
    tags = metadata.read_tags(path, ["DateTimeOriginal", "Make"])
    metadata.write_tags(path, ["-Make=GoPro"])
"""

import atexit
import json
import re
import subprocess
import threading


class MetadataService:
    """Manages a persistent ``jetlag-metadata`` subprocess."""

    def __init__(self):
        self._process = None
        self._lock = threading.Lock()
        self._unavailable = False

    def _ensure_running(self):
        if self._unavailable:
            raise FileNotFoundError("jetlag-metadata not available")
        if self._process is not None and self._process.poll() is None:
            return
        try:
            self._process = subprocess.Popen(
                ["jetlag-metadata"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            self._unavailable = True
            raise

    def _request(self, payload: dict) -> dict:
        """Send a JSON request and read the JSON response."""
        with self._lock:
            self._ensure_running()
            assert self._process is not None
            line = json.dumps(payload) + "\n"
            self._process.stdin.write(line.encode())
            self._process.stdin.flush()

            response_line = self._process.stdout.readline()
            if not response_line:
                raise RuntimeError("jetlag-metadata process closed unexpectedly")

            result = json.loads(response_line.decode())
            if "error" in result:
                raise RuntimeError(f"jetlag-metadata: {result['error']}")
            return result

    def read_tags(self, file_path: str, tags: list[str],
                  extra_args: list[str] | None = None) -> dict:
        """Read specific metadata tags and return a {key: value} dict.

        Matches the ExifTool.read_tags API. The ``extra_args`` parameter
        supports ``-fast2`` (mapped to the ``fast`` protocol field); other
        extra_args are ignored.
        """
        fast = extra_args is not None and "-fast2" in extra_args
        payload = {
            "op": "read",
            "file": str(file_path),
            "tags": list(tags),
        }
        if fast:
            payload["fast"] = True
        return self._request(payload)

    def write_tags(self, file_path: str, tag_args: list[str]) -> bool:
        """Write tags with the same ``["-Tag=Value", ...]`` arg format as ExifTool.

        Returns True when the service reports files were updated.
        """
        tags = {}
        for arg in tag_args:
            cleaned = arg.lstrip("-")
            if "=" not in cleaned:
                continue
            key, value = cleaned.split("=", 1)
            # Strip group prefixes (e.g. "Keys:CreationDate" → "Keys:CreationDate")
            tags[key] = value

        payload = {
            "op": "write",
            "file": str(file_path),
            "tags": tags,
        }
        result = self._request(payload)
        return result.get("updated", False)

    def close(self):
        """Shut down the persistent process."""
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


metadata = MetadataService()
atexit.register(metadata.close)
