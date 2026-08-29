#!/usr/bin/env python3
"""
Cancelling a pipeline run must not leave anything behind.

The app cancels a run by signalling the pipeline's whole process group, so the
run has to end the way Ctrl+C ends a foreground job. First, the subprocesses:
the signal has to shut the metadata service down in order — jetlag-metadata,
and the ``exiftool -stay_open`` process it owns — so that nothing outlives the
run. Killed outright, both are re-parented to launchd and keep running, holding
the vendored binaries and stale exiftool state open. Both metadata backends are
covered, because they leave different trees behind and the app uses the Swift
one. Second, the working directory:
the in-flight staged copy, exiftool's interrupted scratch files and the
directory itself all go with the run, because the working directory is an
implementation detail that only a *failed* run preserves, for inspection.
"""

import contextlib
import os
import shutil
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


def _descendants(root_pid: int) -> dict[int, str]:
    """Every live process whose parent chain leads back to ``root_pid``.

    Descendants rather than process-group members: a child spawned into a group
    of its own is invisible to a group listing, which is exactly how an
    ``exiftool -stay_open`` went on outliving cancelled runs unnoticed.
    """
    parents: dict[int, int] = {}
    commands: dict[int, str] = {}
    listing = subprocess.run(
        ["/bin/ps", "-A", "-o", "pid=,ppid=,command="],
        capture_output=True, text=True,
    ).stdout
    for line in listing.splitlines():
        fields = line.split(maxsplit=2)
        if len(fields) != 3 or not fields[0].isdigit() or not fields[1].isdigit():
            continue
        pid, ppid, command = int(fields[0]), int(fields[1]), fields[2].strip()
        parents[pid] = ppid
        commands[pid] = command

    found = {}
    for pid in parents:
        walker = pid
        seen = set()
        while walker > 1 and walker not in seen:
            seen.add(walker)
            walker = parents.get(walker, 0)
            if walker == root_pid:
                found[pid] = commands[pid]
                break
    return found


def _still_alive(pids) -> list[int]:
    alive = []
    for pid in pids:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        except PermissionError:
            pass
        alive.append(pid)
    return alive


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


@pytest.fixture(params=["python-backend", "swift-backend"])
def running_pipeline(request, tmp_path, source_with_videos):
    """A pipeline mid-run, as its own process-group leader — the shape the app
    launches it in — with the metadata service already spun up, an --apply
    working directory of its own and an interrupted exiftool scratch file in it.

    Run once per metadata backend, because they leave different process trees to
    tear down: the Python backend owns exiftool directly, while the Swift one
    owns jetlag-metadata, which owns exiftool. The app uses the Swift backend, so
    covering only the Python one is how an exiftool that escaped the process
    group went unnoticed.

    Yields (process, pgid, working_dir, descendants).
    """
    environment = dict(os.environ)
    if request.param == "swift-backend":
        environment["JETLAG_METADATA_BINARY"] = str(request.getfixturevalue("jetlag_metadata_binary"))
    else:
        environment["JETLAG_METADATA_BINARY"] = ""

    working_dir = Path(tempfile.mkdtemp(prefix="pipeline_cancel_"))
    pipeline = subprocess.Popen(
        [
            sys.executable, str(MEDIA_PIPELINE_PY),
            "--source", str(source_with_videos),
            "--target", str(tmp_path / "target"),
            "--working-dir", str(working_dir),
            "--timezone", "Pacific/Auckland",
            "--apply",
        ],
        cwd=str(SCRIPT_DIR),
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    pgid = os.getpgid(pipeline.pid)
    try:
        spawned = _wait_until(
            lambda: any("exiftool" in command
                        for command in _descendants(pipeline.pid).values()),
            timeout=60,
        )
        assert spawned, "pipeline never spawned the exiftool a cancel has to clean up"
        assert pipeline.poll() is None, "pipeline finished before it could be cancelled"
        (working_dir / "x_exiftool_tmp").write_bytes(b"interrupted write")
        yield pipeline, pgid, working_dir, _descendants(pipeline.pid)
    finally:
        if pipeline.poll() is None:
            os.killpg(pgid, signal.SIGKILL)
            pipeline.communicate()
        # A test that proves nothing survives must not be handed a clean tree by
        # the fixture, but a test that fails must not leak one either.
        for pid in _still_alive(_descendants(pipeline.pid)):
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.kill(pid, signal.SIGKILL)
        shutil.rmtree(working_dir, ignore_errors=True)


def _entries(working_dir: Path) -> list[str]:
    if not working_dir.exists():
        return []
    return sorted(p.name for p in working_dir.iterdir())


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM],
                         ids=["sigint", "sigterm"])
def test_cancelled_pipeline_leaves_no_metadata_processes(running_pipeline, sig):
    """A cancelled run leaves nothing behind: every process descended from the
    pipeline — jetlag-metadata and the exiftool it owns — is gone once the
    handler has exited, for the interrupt the app sends and for SIGTERM."""
    pipeline, pgid, _, descendants = running_pipeline
    assert descendants, "nothing to clean up — the fixture handed over an empty tree"

    os.killpg(pgid, sig)
    pipeline.communicate(timeout=30)

    stopped = _wait_until(lambda: not _still_alive(descendants), timeout=15)
    assert stopped, (
        "Actual: survived cancel: "
        + ", ".join(f"pid {pid} ({descendants[pid]})" for pid in _still_alive(descendants))
        + ", Expected: no descendant of the pipeline outlives it"
    )


def test_sigterm_exits_through_the_handler(running_pipeline):
    """Cancel is a handled shutdown, not a kill: the pipeline exits with the
    SIGTERM status it chooses rather than dying from the default disposition,
    which is what gives the metadata teardown a chance to run at all."""
    pipeline, pgid, _, _ = running_pipeline

    os.killpg(pgid, signal.SIGTERM)
    pipeline.communicate(timeout=30)

    assert pipeline.returncode == SIGTERM_EXIT_CODE


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM],
                         ids=["sigint", "sigterm"])
def test_cancel_empties_and_removes_the_working_dir(running_pipeline, sig):
    """Cancel takes the working directory with it, whichever signal it arrives as.

    Actual: after the group signal the interrupted exiftool scratch file and the
    directory itself are gone
    Expected: only a failed run preserves the working dir, and a cancel is not
    a failed run — the app's Cancel is Ctrl+C, so SIGINT must behave as SIGTERM
    """
    pipeline, pgid, working_dir, _ = running_pipeline
    assert _entries(working_dir) == ["x_exiftool_tmp"], \
        f"Actual: {_entries(working_dir)}, Expected: the interrupted exiftool write"

    os.killpg(pgid, sig)
    pipeline.communicate(timeout=60)

    assert not working_dir.exists(), \
        f"Actual: working dir survives holding {_entries(working_dir)}, Expected: removed"
