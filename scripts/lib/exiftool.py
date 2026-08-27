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

from __future__ import annotations

import atexit
import re
import collections
import subprocess
import threading



# pids of every exiftool -stay_open child this process has spawned, so a test
# session can confirm none of them are still running at session end.
_spawned_pids: list[int] = []


class ExifTool:
    """Manages a persistent ``exiftool -stay_open True`` subprocess."""

    def __init__(self):
        self._process = None
        self._lock = threading.Lock()
        self._exec_id = 0
        self._unavailable = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

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
        _spawned_pids.append(self._process.pid)
        # Drain stderr continuously: a pipe nobody reads fills after ~16 KB and
        # exiftool then blocks on its next warning before printing the sentinel.
        # Only the tail is kept, for diagnostics.
        self._stderr_tail = collections.deque(maxlen=200)
        threading.Thread(
            target=self._drain_stderr, args=(self._process.stderr,), daemon=True,
        ).start()

    def _drain_stderr(self, stream):
        for raw in iter(stream.readline, b""):
            self._stderr_tail.append(raw.decode(errors="replace").rstrip("\r\n"))

    def execute(self, *args: str) -> str:
        """Send a command and block until the sentinel line is returned."""
        with self._lock:
            self._ensure_running()
            assert self._process is not None  # guaranteed by _ensure_running
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
        """Shut down the persistent process.

        The lock is taken opportunistically: a signal handler runs on the same
        thread that may already hold it inside :meth:`execute`, so blocking here
        would deadlock the shutdown and leave exiftool running. Tearing down
        without it is safe — no further commands are sent either way.
        """
        acquired = self._lock.acquire(blocking=False)
        try:
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
        finally:
            if acquired:
                self._lock.release()


exiftool = ExifTool()
atexit.register(exiftool.close)
