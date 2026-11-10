"""
Running media-pipeline for the pipeline tests, in a process of its own or in this one.

run_pipeline starts media-pipeline.sh in a fresh process with stdout piped, so
the run emits its JSONL events exactly as the app receives them: the tests of the
command line and the JSONL contract use it. run_in_process parses the same
arguments with media-pipeline's own parser and calls lib.pipeline.run() here,
with the same stdout, stderr and exit code, but without a new interpreter and
exiftool per run; tests of what a run does to files and which way it routes
them use it. The temp_workspace and test_profile fixtures that go with both live
in conftest.py.
"""

from __future__ import annotations

import contextlib
import io
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from conftest import create_test_video as _create_video_raw
from cli import media_pipeline
from lib import pipeline
from lib.cli import attach_negative_option_values
from lib.exiftool import exiftool
from lib.pipeline import events

SCRIPT_DIR = Path(__file__).parent.parent
MEDIA_PIPELINE = SCRIPT_DIR / "media-pipeline.sh"


def has_tag_cmd() -> bool:
    return shutil.which("tag") is not None


@dataclass
class PipelineResult:
    """Result from running media-pipeline."""
    stdout: str
    stderr: str
    returncode: int

    @property
    def output(self) -> str:
        """Combined stdout and stderr."""
        return self.stdout + self.stderr


def run_pipeline(args: list[str], cwd: Optional[Path] = None) -> PipelineResult:
    """Run media-pipeline.sh with given args.

    Each invocation gets a working directory outside the target, so assertions
    about what the target holds see only the organized library. The default
    location — <target>/.jetlag-working — has its own coverage in
    TestDefaultWorkingDirIsOnTheTargetVolume.

    Note on output streams:
    - stdout: media-pipeline's own messages (summary, config, per-file status)
    - stderr: child script messages (organize-by-date, fix-timestamp details)
    - combined: use result.output for full output
    """
    if "--working-dir" not in args:
        args = args + ["--working-dir", tempfile.mkdtemp(prefix="pipeline_working_")]
    quoted_args = " ".join(shlex.quote(arg) for arg in args)
    cmd = f"{MEDIA_PIPELINE} {quoted_args}"
    result = subprocess.run(
        cmd,
        shell=True,
        executable="/bin/bash",
        capture_output=True,
        text=True,
        cwd=cwd or SCRIPT_DIR,
    )
    return PipelineResult(
        stdout=result.stdout,
        stderr=result.stderr,
        returncode=result.returncode,
    )


def pipeline_parser():
    """media-pipeline's own argument parser."""
    return media_pipeline.build_parser()


def run_in_process(args: list[str]) -> PipelineResult:
    """run_pipeline's run, made in this process.

    The arguments go through media-pipeline's parser and lib.pipeline.run()
    with a WorkingDir of its own, as main() does; stdout is a pipe, as the app
    sees it, so the JSONL events are emitted. Each run starts with no cached
    metadata, as a new process would.
    """
    if "--working-dir" not in args:
        args = args + ["--working-dir", tempfile.mkdtemp(prefix="pipeline_working_")]
    stdout, stderr = io.StringIO(), io.StringIO()
    returncode = 0
    exiftool.cache.clear()
    machine_output = events._machine_output
    events._machine_output = True
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            parsed = pipeline_parser().parse_args(
                attach_negative_option_values(args))
            pipeline.run(parsed, pipeline.WorkingDir())
    except SystemExit as exit_info:
        code = exit_info.code
        returncode = code if isinstance(code, int) else (0 if code is None else 1)
    finally:
        events._machine_output = machine_output
    return PipelineResult(stdout=stdout.getvalue(), stderr=stderr.getvalue(), returncode=returncode)


def create_test_video(path: Path, media_create_date: str = "2025:10:05 01:00:00"):
    _create_video_raw(path, MediaCreateDate=media_create_date, CreateDate=media_create_date)


def get_file_birth_time(path: Path) -> str:
    """Get file birth time in YYYY:MM:DD HH:MM:SS format."""
    result = subprocess.run(
        ["stat", "-f", "%SB", "-t", "%Y:%m:%d %H:%M:%S", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def get_exif_field(path: Path, field: str) -> str:
    """Get an exif field value."""
    result = subprocess.run(
        ["exiftool", "-s3", f"-{field}", str(path)],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()
