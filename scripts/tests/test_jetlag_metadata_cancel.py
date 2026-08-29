#!/usr/bin/env python3
"""
jetlag-metadata must die the way a foreground job dies under Ctrl+C.

The app cancels a run by signalling the pipeline's process group, so what
matters is not that jetlag-metadata can be killed but that the
``exiftool -stay_open`` process it owns is reached by the same signal and
shuts down with it. Two things make that true: exiftool has to *be* in
jetlag-metadata's process group (a child spawned into a group of its own is
invisible to a group signal), and jetlag-metadata has to handle the signal
rather than die from it, so exiftool is closed in order instead of being
re-parented to launchd still holding its stay_open state.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

from conftest import create_test_video


def _process_group(pid: int) -> int | None:
    result = subprocess.run(
        ["/bin/ps", "-o", "pgid=", "-p", str(pid)],
        capture_output=True, text=True,
    )
    value = result.stdout.strip()
    return int(value) if value.isdigit() else None


def _children(pid: int) -> list[int]:
    listing = subprocess.run(
        ["/bin/ps", "-A", "-o", "pid=,ppid="],
        capture_output=True, text=True,
    ).stdout
    children = []
    for line in listing.split("\n"):
        fields = line.split()
        if len(fields) == 2 and fields[1].isdigit() and int(fields[1]) == pid:
            children.append(int(fields[0]))
    return children


def _wait_until(predicate, timeout: float):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    return predicate()


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError) as exc:
        return isinstance(exc, PermissionError)
    return True


@pytest.fixture
def metadata_with_exiftool(jetlag_metadata_binary, tmp_path):
    """A running jetlag-metadata that has already spun its exiftool up.

    Yields (process, exiftool_pid). Cleaned up with SIGKILL to the group, so a
    test that proves nothing survives is proving it, not being handed it.
    """
    video = tmp_path / "clip.mp4"
    create_test_video(video, DateTimeOriginal="2024:01:01 10:00:00")

    process = subprocess.Popen(
        [str(jetlag_metadata_binary)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        start_new_session=True,
    )
    request = json.dumps({"op": "read", "file": str(video),
                          "tags": ["DateTimeOriginal"], "fast": False})
    process.stdin.write((request + "\n").encode())
    process.stdin.flush()
    response = json.loads(process.stdout.readline().decode())
    assert "DateTimeOriginal" in response, f"jetlag-metadata read failed: {response}"

    exiftool_pids = _wait_until(lambda: _children(process.pid), timeout=10)
    assert exiftool_pids, "jetlag-metadata never spawned exiftool"
    try:
        yield process, exiftool_pids[0]
    finally:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        for pid in exiftool_pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        process.wait(timeout=10)


def test_exiftool_joins_jetlag_metadatas_process_group(metadata_with_exiftool):
    """A single signal to the group has to reach exiftool.

    Actual: exiftool's pgid
    Expected: jetlag-metadata's pgid — a child spawned into a group of its own
    never sees the group signal the app's Cancel sends, and outlives the run
    """
    process, exiftool_pid = metadata_with_exiftool

    assert _process_group(exiftool_pid) == _process_group(process.pid), (
        f"Actual: exiftool pgid {_process_group(exiftool_pid)}, "
        f"Expected: jetlag-metadata's pgid {_process_group(process.pid)}"
    )


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM],
                         ids=["sigint", "sigterm"])
def test_signalled_jetlag_metadata_takes_exiftool_with_it(metadata_with_exiftool, sig):
    """Cancel leaves nothing behind, whichever signal it arrives as.

    Signalling jetlag-metadata alone — not the group — proves the teardown is
    its own doing: without a handler it dies instantly and exiftool is
    re-parented to launchd, still running.
    """
    process, exiftool_pid = metadata_with_exiftool

    os.kill(process.pid, sig)
    process.wait(timeout=15)

    assert process.returncode == -sig or process.returncode == 128 + sig, (
        f"Actual: exit {process.returncode}, Expected: a handled exit for signal {sig}"
    )
    stopped = _wait_until(lambda: not _alive(exiftool_pid), timeout=15)
    assert stopped, f"Actual: exiftool pid {exiftool_pid} still running, Expected: gone"
