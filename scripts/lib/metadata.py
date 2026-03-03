"""
Metadata service wrapper using the jetlag-metadata CLI tool.

Drop-in replacement for lib.exiftool — same read_tags/write_tags API.
Under the hood, communicates with the jetlag-metadata Swift binary via
JSON-over-stdin/stdout.

Usage:
    from lib.metadata import metadata_service as exiftool
    tags = exiftool.read_tags(path, ["DateTimeOriginal", "Make"])
    exiftool.write_tags(path, ["-Make=GoPro"])
"""

import atexit
import json
import shutil
import subprocess
import threading
from pathlib import Path


class MetadataService:
    """Manages a persistent jetlag-metadata subprocess."""

    def __init__(self):
        self._process = None
        self._lock = threading.Lock()
        self._unavailable = False

    def _find_binary(self) -> str:
        tools_dir = Path(__file__).resolve().parent.parent / "tools"
        vendored = tools_dir / "jetlag-metadata"
        if vendored.is_file():
            return str(vendored)
        found = shutil.which("jetlag-metadata")
        if found:
            return found
        raise FileNotFoundError("jetlag-metadata not available")

    def _ensure_running(self):
        if self._unavailable:
            raise FileNotFoundError("jetlag-metadata not available")
        if self._process is not None and self._process.poll() is None:
            return
        try:
            binary = self._find_binary()
            self._process = subprocess.Popen(
                [binary],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            self._unavailable = True
            raise

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
            try:
                return json.loads(response_line)
            except json.JSONDecodeError:
                return {}

    def read_tags(self, file_path: str, tags: list[str],
                  extra_args: list[str] | None = None) -> dict:
        """Read specific metadata tags. Returns {key: value} dict.

        API-compatible with ExifTool.read_tags.
        """
        fast = bool(extra_args and "-fast2" in extra_args)
        return self._call({
            "op": "read",
            "file": str(file_path),
            "tags": tags,
            "fast": fast,
        })

    def write_tags(self, file_path: str, tag_args: list[str]) -> bool:
        """Write tags. Returns True when files were updated.

        API-compatible with ExifTool.write_tags.
        tag_args: list of "-Tag=Value" strings (same format as ExifTool).
        """
        tags = {}
        for arg in tag_args:
            clean = arg.lstrip("-")
            key, _, val = clean.partition("=")
            if key:
                tags[key] = val
        result = self._call({
            "op": "write",
            "file": str(file_path),
            "tags": tags,
        })
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


metadata_service = MetadataService()
atexit.register(metadata_service.close)
