"""
Unified metadata service — abstracts the backend used for reading/writing EXIF.

Tries ``jetlag-metadata`` (Swift CLI) first; falls back to ``exiftool``
(Perl) when the Swift binary is not installed.

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
    """Backend that talks to the ``jetlag-metadata`` Swift CLI."""

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
        tags = {}
        for arg in tag_args:
            cleaned = arg.lstrip("-")
            if "=" not in cleaned:
                continue
            key, value = cleaned.split("=", 1)
            tags[key] = value

        payload = {
            "op": "write",
            "file": str(file_path),
            "tags": tags,
        }
        result = self._request(payload)
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


class _ExifTool:
    """Fallback backend using ``exiftool -stay_open True`` directly."""

    def __init__(self):
        self._process = None
        self._lock = threading.Lock()
        self._exec_id = 0
        self._unavailable = False

    def _ensure_running(self):
        if self._unavailable:
            raise FileNotFoundError("exiftool not available")
        if self._process is not None and self._process.poll() is None:
            return
        try:
            self._process = subprocess.Popen(
                ["exiftool", "-stay_open", "True", "-@", "-"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            self._unavailable = True
            raise

    def execute(self, *args: str) -> str:
        with self._lock:
            self._ensure_running()
            assert self._process is not None
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

    def read_tags(self, file_path: str, tags: list[str],
                  extra_args: list[str] | None = None) -> dict:
        args = ["-s"]
        if extra_args:
            args.extend(extra_args)
        args.extend(f"-{tag}" for tag in tags)
        args.append(str(file_path))

        raw = self.execute(*args)
        data = {}
        for line in raw.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                data[key.strip()] = value.strip()
        return data

    def write_tags(self, file_path: str, tag_args: list[str]) -> bool:
        args = ["-P", "-overwrite_original"] + tag_args + [str(file_path)]
        output = self.execute(*args)
        match = re.search(r"(\d+) image files? updated", output)
        return match is not None and int(match.group(1)) > 0

    def close(self):
        with self._lock:
            if self._process is None or self._process.poll() is not None:
                self._process = None
                return
            try:
                self._process.stdin.write(b"-stay_open\nFalse\n")
                self._process.stdin.flush()
                self._process.wait(timeout=5)
            except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                self._process.kill()
                self._process.wait()
            self._process = None


def _create_backend():
    """Try jetlag-metadata first; fall back to exiftool."""
    import shutil
    if shutil.which("jetlag-metadata"):
        return MetadataService()
    return _ExifTool()


metadata = _create_backend()
atexit.register(metadata.close)
