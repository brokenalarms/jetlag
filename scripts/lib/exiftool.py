"""
Persistent ExifTool batch-mode wrapper.

ExifTool's -stay_open flag keeps a single Perl process alive, accepting
commands via stdin and returning results via stdout. This eliminates the
~100-200ms cold-start overhead per invocation.

Usage:
    from lib.exiftool import exiftool
    tags = exiftool.read_tags(path, ["DateTimeOriginal", "Make"])
    exiftool.write_tags(path, ["-Make=GoPro"])
"""

import atexit
import re
import subprocess
import threading

from lib.tools import resolve as resolve_tool


class ExifTool:
    """Manages a persistent ``exiftool -stay_open True`` subprocess."""

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
            exe = resolve_tool("exiftool")
            self._process = subprocess.Popen(
                [exe, "-stay_open", "True", "-@", "-"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            self._unavailable = True
            raise FileNotFoundError(
                "exiftool not found. Install via: brew install exiftool"
            )

    def execute(self, *args: str) -> str:
        """Send a command and block until the sentinel line is returned."""
        with self._lock:
            self._ensure_running()
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
        """Read specific EXIF tags and return a {key: value} dict.

        Uses ``-s`` (short output) so keys are bare tag names.
        """
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
        """Write tags with ``-P -overwrite_original``.

        Returns True when exiftool reports files were updated.
        """
        args = ["-P", "-overwrite_original"] + tag_args + [str(file_path)]
        output = self.execute(*args)
        match = re.search(r"(\d+) image files? updated", output)
        return match is not None and int(match.group(1)) > 0

    def close(self):
        """Shut down the persistent process."""
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


exiftool = ExifTool()
atexit.register(exiftool.close)
