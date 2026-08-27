#!/usr/bin/env python3
"""
Cancelling a pipeline run must not leave its metadata subprocesses behind.

The app cancels a run by signalling the pipeline's whole process group. These
tests cover the Python half of that contract: SIGTERM has to shut the metadata
service down in order — jetlag-metadata, and the ``exiftool -stay_open`` process
it owns — so that nothing outlives the run. Killed outright, both are re-parented
to launchd and keep running, holding the vendored binaries and stale exiftool
state open.
"""

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from conftest import create_test_video

SCRIPT_DIR = Path(__file__).parent.parent
MEDIA_PIPELINE_PY = SCRIPT_DIR / "media-pipeline.py"

SIGTERM_EXIT_CODE = 128 + signal.SIGTERM


def _group_members(pgid: int) -> list[str]:
    """Command lines of every live process in the given process group."""
    listing = subprocess.run(
        ["/bin/ps", "-A", "-o", "pgid=,command="],
        capture_output=True, text=True,
    ).stdout
    members = []
    for line in listing.splitlines():
        head, _, command = line.strip().partition(" ")
        if head.isdigit() and int(head) == pgid and command.strip():
            members.append(command.strip())
    return members


def _wait_until(predicate, timeout: float):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    return predicate()


@pytest.fixture(scope="module")
def source_with_videos(tmp_path_factory):
    """Real videos followed by a named pipe with no writer.

    A run over a handful of small files is over in a fraction of a second — far
    too fast to cancel reliably. The pipe parks the run exactly where the leak
    happens: exiftool blocked opening it, mid-command, with the pipeline waiting
    on a reply it will never get.
    """
    source = tmp_path_factory.mktemp("cancel_source")
    for index in range(2):
        create_test_video(source / f"clip{index}.mp4",
                          DateTimeOriginal="2024:01:01 10:00:00")
    os.mkfifo(source / "zz-never-readable.mp4")
    return source


@pytest.fixture
def running_pipeline(tmp_path, source_with_videos):
    """A pipeline mid-run, as its own process-group leader — the shape the app
    launches it in — with the metadata service already spun up."""
    pipeline = subprocess.Popen(
        [
            sys.executable, str(MEDIA_PIPELINE_PY),
            "--source", str(source_with_videos),
            "--target", str(tmp_path / "target"),
            "--working-dir", tempfile.mkdtemp(prefix="pipeline_cancel_"),
            "--timezone", "Pacific/Auckland",
        ],
        cwd=str(SCRIPT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    pgid = os.getpgid(pipeline.pid)
    try:
        spawned = _wait_until(lambda: len(_group_members(pgid)) > 1, timeout=60)
        assert spawned, "pipeline never spawned a metadata subprocess to clean up"
        assert pipeline.poll() is None, "pipeline finished before it could be cancelled"
        yield pipeline, pgid
    finally:
        if pipeline.poll() is None:
            os.killpg(pgid, signal.SIGKILL)
            pipeline.communicate()


def test_cancelled_pipeline_leaves_no_metadata_processes(running_pipeline):
    """A cancelled run leaves nothing behind: after SIGTERM the pipeline's
    process group is empty — no pipeline, no jetlag-metadata, no exiftool."""
    pipeline, pgid = running_pipeline

    os.kill(pipeline.pid, signal.SIGTERM)
    pipeline.communicate(timeout=30)

    stopped = _wait_until(lambda: not _group_members(pgid), timeout=15)
    assert stopped, f"processes survived cancel: {_group_members(pgid)}"


def test_sigterm_exits_through_the_handler(running_pipeline):
    """Cancel is a handled shutdown, not a kill: the pipeline exits with the
    SIGTERM status it chooses rather than dying from the default disposition,
    which is what gives the metadata teardown a chance to run at all."""
    pipeline, _ = running_pipeline

    os.kill(pipeline.pid, signal.SIGTERM)
    pipeline.communicate(timeout=30)

    assert pipeline.returncode == SIGTERM_EXIT_CODE
