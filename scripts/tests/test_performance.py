#!/usr/bin/env python3
"""
Performance regression gate for media-pipeline.

Runs a full pipeline (fix-timestamp) against a baseline checkout of the
scripts and against the current working tree, interleaved (baseline,
candidate, baseline, candidate, ...) so that a runner slowdown mid-run drags
both sides down together instead of only whichever side happened to run
during the slow window. Compares the medians of each side.

Usage:
    pytest tests/test_performance.py -v -s --perf-baseline-scripts-dir=/path/to/baseline/scripts

Without --perf-baseline-scripts-dir the test has nothing to compare against
and is skipped.

scripts/tests/perf-gate.sh sets this up for you: it checks out origin/main's
scripts into a temp directory and passes it as the baseline. See
docs/testing.md for how REGRESSION_THRESHOLD was measured.
"""

import shlex
import statistics
import subprocess
import tempfile
import time
from pathlib import Path

import pytest
import yaml

SCRIPT_DIR = Path(__file__).parent.parent
MEDIA_PIPELINE = SCRIPT_DIR / "media-pipeline.sh"

# See docs/testing.md "Performance gate noise band" for how this was measured.
REGRESSION_THRESHOLD = 0.30
ROUNDS = 3
# Enough files to amortise process startup, small enough to keep the gate fast.
FILE_COUNT = 40

from conftest import create_test_video as _create_video_raw


def create_test_video(path: Path, media_create_date: str = "2025:10:05 01:00:00"):
    _create_video_raw(path, MediaCreateDate=media_create_date, CreateDate=media_create_date)


def run_pipeline(pipeline_script: Path, args: list[str]) -> subprocess.CompletedProcess:
    """Run a media-pipeline.sh with given args, isolating the working directory
    (the shared default collides across parallel workers)."""
    if "--working-dir" not in args:
        args = args + ["--working-dir", tempfile.mkdtemp(prefix="pipeline_working_")]
    quoted_args = " ".join(shlex.quote(arg) for arg in args)
    cmd = f"{pipeline_script} {quoted_args}"
    return subprocess.run(
        cmd, shell=True, executable="/bin/bash",
        capture_output=True, text=True, cwd=pipeline_script.parent,
    )


def _write_perf_profile(profiles_path: Path, source: Path, target: Path) -> None:
    with open(profiles_path) as f:
        profiles = yaml.safe_load(f)
    profiles.setdefault("profiles", {})["_perf_test"] = {
        "source_dir": str(source),
        "ready_dir": str(target),
        "file_extensions": [".mp4"],
    }
    with open(profiles_path, "w") as f:
        yaml.dump(profiles, f, default_flow_style=False, sort_keys=False)


def _warmup(pipeline_script: Path, profiles_path: Path) -> None:
    """Run once, untimed, so one-time costs (venv creation, first exiftool spawn)
    land here instead of inflating whichever round happens to run first."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        source = workspace / "source"
        target = workspace / "target"
        source.mkdir()
        target.mkdir()
        create_test_video(source / "warmup.mp4")
        _write_perf_profile(profiles_path, source, target)
        run_pipeline(pipeline_script, [
            "--profile", "_perf_test",
            "--source", str(source),
            "--timezone", "+0900",
            "--tasks", "fix-timestamp",
            "--apply",
        ])


def _timed_run(pipeline_script: Path, profiles_path: Path) -> float:
    """Write file_count fresh videos, run fix-timestamp over them, return elapsed seconds."""
    timestamps = [
        f"2025:10:{5 + i:02d} {i:02d}:00:00"
        for i in range(FILE_COUNT)
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        source = workspace / "source"
        target = workspace / "target"
        source.mkdir()
        target.mkdir()

        for j, ts in enumerate(timestamps):
            create_test_video(source / f"file_{j}.mp4", media_create_date=ts)

        _write_perf_profile(profiles_path, source, target)

        t0 = time.perf_counter()
        result = run_pipeline(pipeline_script, [
            "--profile", "_perf_test",
            "--source", str(source),
            "--timezone", "+0900",
            "--tasks", "fix-timestamp",
            "--apply",
        ])
        elapsed = time.perf_counter() - t0
        assert result.returncode == 0, (
            f"pipeline failed during timing run — measurement is meaningless.\n"
            f"stderr: {result.stderr[-500:]}"
        )
        return elapsed


class TestPerformance:
    """Performance regression gate — pipeline-level end-to-end, interleaved."""

    def _check(self, name: str, baseline_times: list[float], candidate_times: list[float], request):
        baseline_median = statistics.median(baseline_times)
        candidate_median = statistics.median(candidate_times)
        ratio = candidate_median / baseline_median if baseline_median > 0 else 1.0
        delta_pct = (ratio - 1.0) * 100
        if delta_pct > 0:
            status = f"SLOWER +{delta_pct:.0f}% ({candidate_median:.2f}s vs baseline {baseline_median:.2f}s)"
        else:
            status = f"faster {delta_pct:.0f}% ({candidate_median:.2f}s vs baseline {baseline_median:.2f}s)"
        print(f"\n  {name}: {status}")

        result = {
            "name": name,
            "elapsed": round(candidate_median, 3),
            "baseline": round(baseline_median, 3),
            "delta_pct": round(delta_pct, 1),
            "regression": ratio > (1 + REGRESSION_THRESHOLD),
        }
        request.config._perf_results.append(result)

        assert ratio <= (1 + REGRESSION_THRESHOLD), (
            f"{name} regression: {candidate_median:.2f}s is {delta_pct:.0f}% slower than baseline "
            f"{baseline_median:.2f}s (threshold {REGRESSION_THRESHOLD*100:.0f}%)"
        )

    def test_media_pipeline(self, request):
        """media-pipeline: fix-timestamp on multiple files, baseline vs working tree.

        Baseline and candidate runs are interleaved (A B A B A B) rather than run
        as two contiguous blocks, so a runner slowdown during the run hits both
        sides instead of just whichever block happened to be running at the time.
        """
        baseline_dir = request.config.getoption("--perf-baseline-scripts-dir", default=None)
        if not baseline_dir:
            print("\n  media_pipeline: no --perf-baseline-scripts-dir given — skipping comparison")
            pytest.skip("no baseline scripts dir given")

        baseline_scripts = Path(baseline_dir)
        baseline_pipeline = baseline_scripts / "media-pipeline.sh"
        baseline_profiles = baseline_scripts / "media-profiles.yaml"
        candidate_profiles = SCRIPT_DIR / "media-profiles.yaml"

        candidate_original = candidate_profiles.read_text()
        baseline_original = baseline_profiles.read_text()

        baseline_times = []
        candidate_times = []
        try:
            _warmup(baseline_pipeline, baseline_profiles)
            _warmup(MEDIA_PIPELINE, candidate_profiles)
            for _ in range(ROUNDS):
                baseline_times.append(_timed_run(baseline_pipeline, baseline_profiles))
                candidate_times.append(_timed_run(MEDIA_PIPELINE, candidate_profiles))
        finally:
            candidate_profiles.write_text(candidate_original)
            baseline_profiles.write_text(baseline_original)

        self._check("media_pipeline", baseline_times, candidate_times, request)
