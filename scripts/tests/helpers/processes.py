"""The exiftool -stay_open children a test run spawned and left running."""

from __future__ import annotations

import subprocess

import lib.exiftool as exiftool_module


def leaked_metadata_pids():
    """Pids of exiftool -stay_open children this process spawned (via
    lib.exiftool) that are still alive."""
    tracked = [(pid, "exiftool") for pid in exiftool_module._spawned_pids]
    leaked = []
    for pid, name in tracked:
        result = subprocess.run(
            ["ps", "-ww", "-p", str(pid), "-o", "command="],
            capture_output=True, text=True,
        )
        cmd = result.stdout.strip()
        if cmd and name in cmd:
            leaked.append(f"pid {pid} ({cmd})")
    return leaked
