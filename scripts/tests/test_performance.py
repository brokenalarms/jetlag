#!/usr/bin/env python3
"""
Performance snapshot harness for media-pipeline.

Measures wall-clock time for a full pipeline run (fix-timestamp + organize)
and compares against a saved baseline to detect speed regressions.

Usage:
    pytest tests/test_performance.py -v -s                  # compare against baseline
    pytest tests/test_performance.py -v -s --perf-baseline  # record new baseline

The baseline file (tests/perf_baseline.json) is machine-specific and gitignored.
Record it once on your dev machine with --perf-baseline, then subsequent runs
compare against it. Delete the file and re-record after intentional perf changes.
"""

import json
import shlex
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest
import yaml

SCRIPT_DIR = Path(__file__).parent.parent
MEDIA_PIPELINE = SCRIPT_DIR / "media-pipeline.sh"
DEFAULT_BASELINE_FILE = Path(__file__).parent / "perf_baseline.json"
REGRESSION_THRESHOLD = 0.05  # 5% slower than baseline = regression
TIMED_RUNS = 3


def _baseline_path(config) -> Path:
    custom = config.getoption("--perf-baseline-file", default=None)
    return Path(custom) if custom else DEFAULT_BASELINE_FILE


def load_baseline(config) -> dict:
    path = _baseline_path(config)
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save_baseline(config, results: dict):
    path = _baseline_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=2) + "\n")


from conftest import create_test_video as _create_video_raw


def create_test_video(path: Path, media_create_date: str = "2025:10:05 01:00:00"):
    _create_video_raw(path, MediaCreateDate=media_create_date, CreateDate=media_create_date)


def run_pipeline(args: list[str]) -> subprocess.CompletedProcess:
    """Run media-pipeline.sh with given args."""
    quoted_args = " ".join(shlex.quote(arg) for arg in args)
    cmd = f"{MEDIA_PIPELINE} {quoted_args}"
    return subprocess.run(
        cmd, shell=True, executable="/bin/bash",
        capture_output=True, text=True, cwd=SCRIPT_DIR,
    )


class TestPerformance:
    """Performance snapshot — pipeline-level end-to-end."""

    def _check(self, name: str, elapsed: float, request):
        """Compare elapsed time against baseline, or record if --perf-baseline."""
        config = request.config
        baseline = load_baseline(config)
        recording = config.getoption("--perf-baseline", default=False)

        if recording:
            baseline[name] = round(elapsed, 3)
            save_baseline(config, baseline)
            print(f"\n  {name}: {elapsed:.2f}s (baseline recorded)")
            return

        if name not in baseline:
            print(f"\n  {name}: {elapsed:.2f}s (no baseline — run with --perf-baseline to record)")
            return

        base = baseline[name]
        ratio = elapsed / base if base > 0 else 1.0
        delta_pct = (ratio - 1.0) * 100
        if delta_pct > 0:
            status = f"SLOWER +{delta_pct:.0f}% ({elapsed:.2f}s vs baseline {base:.2f}s)"
        else:
            status = f"faster {delta_pct:.0f}% ({elapsed:.2f}s vs baseline {base:.2f}s)"
        print(f"\n  {name}: {status}")

        result = {
            "name": name,
            "elapsed": round(elapsed, 3),
            "baseline": round(base, 3),
            "delta_pct": round(delta_pct, 1),
            "regression": ratio > (1 + REGRESSION_THRESHOLD),
        }
        config._perf_results.append(result)

        assert ratio <= (1 + REGRESSION_THRESHOLD), (
            f"{name} regression: {elapsed:.2f}s is {delta_pct:.0f}% slower than baseline {base:.2f}s "
            f"(threshold {REGRESSION_THRESHOLD*100:.0f}%)"
        )

    def test_media_pipeline(self, request):
        """media-pipeline: fix-timestamp + organize on multiple files."""
        profiles_path = SCRIPT_DIR / "media-profiles.yaml"
        original_yaml = profiles_path.read_text()

        file_count = 100
        timestamps = [
            f"2025:10:{5 + i:02d} {i:02d}:00:00"
            for i in range(file_count)
        ]

        times = []
        try:
            for _ in range(TIMED_RUNS):
                with tempfile.TemporaryDirectory() as tmpdir:
                    workspace = Path(tmpdir)
                    source = workspace / "source"
                    target = workspace / "target"
                    source.mkdir()
                    target.mkdir()

                    for j, ts in enumerate(timestamps):
                        create_test_video(source / f"file_{j}.mp4", media_create_date=ts)

                    with open(profiles_path) as f:
                        profiles = yaml.safe_load(f)
                    profiles["profiles"]["_perf_test"] = {
                        "source_dir": str(source),
                        "ready_dir": str(target),
                        "file_extensions": [".mp4"],
                    }
                    with open(profiles_path, "w") as f:
                        yaml.dump(profiles, f, default_flow_style=False, sort_keys=False)

                    t0 = time.perf_counter()
                    run_pipeline([
                        "--profile", "_perf_test",
                        "--source", str(source),
                        "--timezone", "+0900",
                        "--tasks", "fix-timestamp",
                        "--apply",
                    ])
                    times.append(time.perf_counter() - t0)
        finally:
            profiles_path.write_text(original_yaml)

        self._check("media_pipeline", statistics.median(times), request)
