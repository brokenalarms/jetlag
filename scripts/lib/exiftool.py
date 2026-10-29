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
import os
import re
import subprocess
import threading
from pathlib import Path

EXIFTOOL_CONFIG = str(Path(__file__).parent / "exiftool-jetlag.config")

# The exiftool to start: the one on PATH (scripts/tools first, via the .sh
# wrappers) unless JETLAG_EXIFTOOL names another. Tests point it at a stand-in
# that counts calls before passing them to the real one.
EXIFTOOL_BINARY = os.environ.get("JETLAG_EXIFTOOL") or "exiftool"

# pids of every exiftool -stay_open child this process has spawned, so a test
# session can confirm none of them are still running at session end.
_spawned_pids: list[int] = []

_STDERR_MARKER = re.compile(r"^\{stderr\d+\}$")


class MetadataWriteRefused(Exception):
    """exiftool left a file unwritten; the message is exiftool's own reason."""


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
                [EXIFTOOL_BINARY, "-config", EXIFTOOL_CONFIG, "-stay_open", "True", "-@", "-"],
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
        # Each command's lines are handed to it at its marker; see _run.
        self._stderr_lines: list[str] = []
        self._stderr_closed = False
        self._stderr_changed = threading.Condition()
        threading.Thread(
            target=self._drain_stderr, args=(self._process.stderr,), daemon=True,
        ).start()

    def _drain_stderr(self, stream):
        for raw in iter(stream.readline, b""):
            with self._stderr_changed:
                self._stderr_lines.append(raw.decode(errors="replace").rstrip("\r\n"))
                self._stderr_changed.notify_all()
        with self._stderr_changed:
            self._stderr_closed = True
            self._stderr_changed.notify_all()

    def _run(self, *args: str, wait_for_stderr: bool = False) -> tuple[str, list[str]]:
        """Send a command; return its stdout and the stderr lines it produced.

        stdout and stderr are separate pipes, so the stdout sentinel says nothing
        about how much of the command's stderr has arrived. -echo4 has exiftool
        print a marker to stderr once the command is processed, after its errors
        and warnings; it goes first because it acts at the end wherever it is, and
        the file stays the last argument. Only a caller that needs the command's
        stderr waits for its marker; the rest return as soon as stdout is done.
        """
        with self._lock:
            self._ensure_running()
            assert self._process is not None  # guaranteed by _ensure_running
            self._exec_id += 1
            sentinel = f"{{ready{self._exec_id}}}"
            stderr_marker = f"{{stderr{self._exec_id}}}"

            payload = "\n".join(["-echo4", stderr_marker, *args]) + "\n" + f"-execute{self._exec_id}\n"
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

            with self._stderr_changed:
                if wait_for_stderr:
                    self._stderr_changed.wait_for(
                        lambda: stderr_marker in self._stderr_lines or self._stderr_closed)
                return "\n".join(output_lines), self._take_stderr(stderr_marker)

    def _take_stderr(self, marker: str) -> list[str]:
        """The stderr lines that came just before marker, dropping every finished
        command's lines so the buffer never outgrows the commands still in flight.

        Commands run one at a time, so each command's lines sit between the marker
        before it and its own.
        """
        lines = self._stderr_lines
        markers = [i for i, line in enumerate(lines) if _STDERR_MARKER.match(line)]
        if not markers:
            return []
        own = lines.index(marker) if marker in lines else None
        taken = []
        if own is not None:
            start = max((i for i in markers if i < own), default=-1) + 1
            taken = lines[start:own]
        del lines[:markers[-1] + 1]
        return taken

    def execute(self, *args: str) -> str:
        """Send a command and block until the sentinel line is returned."""
        return self._run(*args)[0]

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

        Returns True when exiftool reports files were updated, False when it found
        nothing to change. Raises MetadataWriteRefused when exiftool could not write
        the file at all, so a refusal can never pass for a write.
        """
        args = ["-P", "-overwrite_original"] + tag_args + [str(file_path)]
        output, diagnostics = self._run(*args, wait_for_stderr=True)
        if re.search(r"\d+ files? weren't updated due to errors", output):
            errors = [
                line.removeprefix("Error: ").removesuffix(f" - {file_path}")
                for line in diagnostics if line.startswith("Error: ")
            ]
            raise MetadataWriteRefused("; ".join(errors) or output.strip())
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
