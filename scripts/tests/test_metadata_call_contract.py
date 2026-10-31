#!/usr/bin/env python3
"""
The pipeline's metadata contract: each file is read once, its metadata kept in
memory, and written at most once. A dry run is one exiftool call per file, an apply
two. Every exiftool call costs a round-trip, and every write rewrites the whole file
— for a 16 GB clip, a full copy — so an extra one is a real cost no timing test on a
shared machine can resolve. These counts are exact; changing one means changing the
contract here, with the reason in the commit.

Calls are counted by running the pipeline against tests/metadata_call_counter.py,
a stand-in exiftool that logs each command and passes it to the real one.
"""

import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

from conftest import create_insta360_file, create_test_video

SCRIPT_DIR = Path(__file__).parent.parent
MEDIA_PIPELINE = SCRIPT_DIR / "media-pipeline.sh"
COUNTER = Path(__file__).parent / "metadata_call_counter.py"
EXIFTOOL = SCRIPT_DIR / "tools" / "exiftool"
FILE_COUNT = 3


@pytest.fixture
def workspace(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    for i in range(FILE_COUNT):
        # No Make/Model, so tagging has something to write.
        create_test_video(
            source / f"VID_2025100{i + 1}_100000.mp4",
            **{"QuickTime:CreateDate": f"2025:10:0{i + 1} 01:00:00",
               "QuickTime:MediaCreateDate": f"2025:10:0{i + 1} 01:00:00"},
        )

    profiles = yaml.safe_load((SCRIPT_DIR / "media-profiles.yaml").read_text())
    profiles["profiles"]["_contract"] = {
        "source_dir": str(source),
        "ready_dir": str(target),
        "file_extensions": [".mp4"],
        "exif": {"make": "Test", "model": "Camera"},
    }
    profiles_path = tmp_path / "media-profiles.yaml"
    profiles_path.write_text(yaml.dump(profiles, sort_keys=False))
    return {"root": tmp_path, "source": source, "profiles": profiles_path}


def metadata_calls(workspace, tasks: list[str], apply: bool) -> dict:
    """Run the pipeline and return the exiftool calls it made, counted by op."""
    log = workspace["root"] / "metadata-calls.jsonl"
    log.write_text("")
    args = [
        "--profile", "_contract",
        "--source", str(workspace["source"]),
        "--timezone", "+0900",
        "--tasks", *tasks,
        "--working-dir", tempfile.mkdtemp(prefix="pipeline_working_"),
    ] + (["--apply"] if apply else [])
    env = dict(
        os.environ,
        JETLAG_EXIFTOOL=str(COUNTER),
        REAL_EXIFTOOL=str(EXIFTOOL),
        METADATA_CALL_LOG=str(log),
        JETLAG_PROFILES_FILE=str(workspace["profiles"]),
    )
    result = subprocess.run(
        f"{MEDIA_PIPELINE} {' '.join(shlex.quote(a) for a in args)}",
        shell=True, executable="/bin/bash", capture_output=True, text=True,
        cwd=SCRIPT_DIR, env=env,
    )
    assert result.returncode == 0, result.stderr[-1500:]

    calls = [json.loads(line) for line in log.read_text().splitlines()]
    return {
        "read": sum(1 for c in calls if c["op"] == "read"),
        "write": sum(1 for c in calls if c["op"] == "write"),
    }


@pytest.mark.parametrize("tasks", [["fix-timestamp"], ["tag", "fix-timestamp"], ["tag"]])
def test_dry_run_reads_each_file_once(workspace, tasks):
    assert metadata_calls(workspace, tasks, apply=False) == {"read": FILE_COUNT, "write": 0}


@pytest.mark.parametrize("tasks", [["fix-timestamp"], ["tag", "fix-timestamp"], ["tag"]])
def test_apply_reads_and_writes_each_file_once(workspace, tasks):
    assert metadata_calls(workspace, tasks, apply=True) == {"read": FILE_COUNT, "write": FILE_COUNT}


def test_insv_costs_one_read(workspace):
    """An .insv's embedded-data read is the same single read, not an extra call."""
    for mp4 in workspace["source"].glob("*.mp4"):
        mp4.unlink()
    create_insta360_file(workspace["source"] / "VID_20251001_100000.insv", "Insta360 X4")
    profiles = yaml.safe_load(workspace["profiles"].read_text())
    profiles["profiles"]["_contract"]["file_extensions"] = [".insv"]
    workspace["profiles"].write_text(yaml.dump(profiles, sort_keys=False))

    assert metadata_calls(workspace, ["tag", "fix-timestamp"], apply=False) == {"read": 1, "write": 0}
