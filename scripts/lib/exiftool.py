"""Shared exiftool utilities for media scripts.

Provides ExifToolStayOpen — a minimal wrapper around exiftool's -stay_open
protocol that keeps one Perl process alive across all operations, eliminating
per-call startup overhead (~0.15s per call on typical hardware).

Usage:
    # As context manager (preferred — auto-cleanup):
    with ExifToolStayOpen() as et:
        data = et.read_tags("file.mp4", ["DateTimeOriginal", "Make"])
        et.write_tags("file.mp4", ["-Make=GoPro", "-Model=HERO12"])

    # Standalone scripts that may or may not receive a handle:
    def read_exif_data(file_path, et=None):
        if et:
            return et.read_tags(file_path, fields)
        else:
            return subprocess_fallback(file_path, fields)
"""

import subprocess


class ExifToolStayOpen:
    """Minimal stay_open wrapper using exiftool's -stay_open protocol.

    Keeps one exiftool process alive across all operations, avoiding
    repeated Perl startup overhead. Commands are sent via stdin with
    -execute as the command terminator, responses read until {ready}.
    """

    def __init__(self):
        self._proc = None

    def start(self):
        self._proc = subprocess.Popen(
            ["exiftool", "-stay_open", "True", "-@", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def stop(self):
        if self._proc:
            self._proc.stdin.write(b"-stay_open\nFalse\n")
            self._proc.stdin.flush()
            self._proc.wait(timeout=5)
            self._proc = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()

    def execute(self, *args: str) -> str:
        """Send a command and read the response up to the {ready} sentinel."""
        cmd = "\n".join(args) + "\n-execute\n"
        self._proc.stdin.write(cmd.encode("utf-8"))
        self._proc.stdin.flush()

        output = []
        while True:
            line = self._proc.stdout.readline()
            if not line:
                break
            line_str = line.decode("utf-8", errors="replace")
            if line_str.strip() == "{ready}":
                break
            output.append(line_str)
        return "".join(output)

    def read_tags(self, file_path: str, fields: list[str]) -> dict:
        """Read specified EXIF fields from a file.

        Returns dict mapping field names to values, same format as
        parsing exiftool -s output.
        """
        args = ["-s"] + [f"-{f}" for f in fields] + [file_path]
        raw = self.execute(*args)
        data = {}
        for line in raw.strip().split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                data[key.strip()] = value.strip()
        return data

    def write_tags(self, file_path: str, field_args: list[str]) -> bool:
        """Write EXIF fields to a file.

        field_args: list of "-Field=Value" strings, same format as
        subprocess exiftool calls.

        Returns True if exiftool reported success.
        """
        args = ["-P", "-overwrite_original"] + field_args + [file_path]
        output = self.execute(*args)
        # exiftool prints "1 image files updated" on success
        return "updated" in output.lower()
