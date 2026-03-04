"""
Metadata service — same read_tags/write_tags API backed by either the
jetlag-metadata Swift CLI (preferred) or ExifTool directly (fallback).

Usage:
    from lib.metadata import metadata_service as exiftool
    tags = exiftool.read_tags(path, ["DateTimeOriginal", "Make"])
    exiftool.write_tags(path, ["-Make=GoPro"])
"""

import atexit
import json
import re
import shutil
import subprocess
import threading
from pathlib import Path


class _JetlagMetadataBackend:
    """JSON-over-stdin/stdout protocol with the jetlag-metadata Swift CLI."""

    def __init__(self, binary: str):
        self._process = subprocess.Popen(
            [binary],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def read_tags(self, file_path: str, tags: list[str], fast: bool) -> dict:
        return self._call({
            "op": "read",
            "file": str(file_path),
            "tags": tags,
            "fast": fast,
        })

    def write_tags(self, file_path: str, tags: dict) -> bool:
        result = self._call({
            "op": "write",
            "file": str(file_path),
            "tags": tags,
        })
        return result.get("updated", False)

    def _call(self, request: dict) -> dict:
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

    def close(self):
        if self._process.poll() is not None:
            return
        try:
            self._process.stdin.close()
            self._process.wait(timeout=5)
        except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
            self._process.kill()
            self._process.wait()


class _ExifToolBackend:
    """Direct ExifTool -stay_open protocol — fallback when jetlag-metadata
    is unavailable (e.g. Linux CI without Swift)."""

    def __init__(self):
        self._process = subprocess.Popen(
            ["exiftool", "-stay_open", "True", "-@", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._exec_id = 0

    def read_tags(self, file_path: str, tags: list[str], fast: bool) -> dict:
        args = ["-s"]
        if fast:
            args.append("-fast2")
        args.extend(f"-{tag}" for tag in tags)
        args.append(str(file_path))
        raw = self._execute(*args)
        data = {}
        for line in raw.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                data[key.strip()] = value.strip()
        return data

    def write_tags(self, file_path: str, tags: dict) -> bool:
        tag_args = [f"-{k}={v}" for k, v in tags.items()]
        args = ["-P", "-overwrite_original"] + tag_args + [str(file_path)]
        output = self._execute(*args)
        match = re.search(r"(\d+) image files? updated", output)
        return match is not None and int(match.group(1)) > 0

    def _execute(self, *args: str) -> str:
        self._exec_id += 1
        sentinel = f"{{ready{self._exec_id}}}"
        payload = "\n".join(args) + "\n" + f"-execute{self._exec_id}\n"
        self._process.stdin.write(payload.encode())
        self._process.stdin.flush()
        output_lines = []
        while True:
            line = self._process.stdout.readline()
            if not line:
                break
            decoded = line.decode().rstrip("\r\n")
            if decoded == sentinel:
                break
            output_lines.append(decoded)
        return "\n".join(output_lines)

    def close(self):
        if self._process.poll() is not None:
            return
        try:
            self._process.stdin.write(b"-stay_open\nFalse\n")
            self._process.stdin.flush()
            self._process.wait(timeout=5)
        except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
            self._process.kill()
            self._process.wait()


class MetadataService:
    """Unified API that delegates to jetlag-metadata or ExifTool."""

    def __init__(self):
        self._backend = None
        self._lock = threading.Lock()

    def _ensure_backend(self):
        if self._backend is not None:
            return
        binary = self._find_jetlag_metadata()
        if binary:
            self._backend = _JetlagMetadataBackend(binary)
        else:
            self._backend = _ExifToolBackend()

    @staticmethod
    def _find_jetlag_metadata() -> str | None:
        tools_dir = Path(__file__).resolve().parent.parent / "tools"
        vendored = tools_dir / "jetlag-metadata"
        if vendored.is_file():
            return str(vendored)
        found = shutil.which("jetlag-metadata")
        return found

    def read_tags(self, file_path: str, tags: list[str],
                  extra_args: list[str] | None = None) -> dict:
        fast = bool(extra_args and "-fast2" in extra_args)
        with self._lock:
            self._ensure_backend()
            return self._backend.read_tags(file_path, tags, fast)

    def write_tags(self, file_path: str, tag_args: list[str]) -> bool:
        tags = {}
        for arg in tag_args:
            clean = arg.lstrip("-")
            key, _, val = clean.partition("=")
            if key:
                tags[key] = val
        with self._lock:
            self._ensure_backend()
            return self._backend.write_tags(file_path, tags)

    def close(self):
        with self._lock:
            if self._backend is not None:
                self._backend.close()
                self._backend = None


metadata_service = MetadataService()
atexit.register(metadata_service.close)
