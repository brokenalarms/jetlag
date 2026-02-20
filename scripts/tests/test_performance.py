#!/usr/bin/env python3
"""
Performance snapshot harness for base scripts.

Measures wall-clock time for each script processing a single file and compares
against a saved baseline to detect speed regressions.

Baseline file (tests/perf_baseline.json) is auto-created on first run.
Delete it to reset and record a new baseline after intentional perf improvements.
"""

import json
import shutil
import statistics
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).parent.parent
BASELINE_FILE = Path(__file__).parent / "perf_baseline.json"
REGRESSION_THRESHOLD = 0.05  # 5% slower than baseline = regression
TIMED_RUNS = 3


@pytest.fixture(scope="module")
def source_mp4(tmp_path_factory):
    """Create a source test mp4 with DateTimeOriginal set (no Keys:CreationDate)."""
    tmp = tmp_path_factory.mktemp("perf_src")
    path = tmp / "source.mp4"
    subprocess.run([
        "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
        "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p", str(path)
    ], capture_output=True, check=True)
    # Set DateTimeOriginal with timezone so fix-media-timestamp has something to work from
    subprocess.run([
        "exiftool", "-overwrite_original",
        "-DateTimeOriginal=2024:06:15 10:30:00+09:00",
        str(path)
    ], capture_output=True, check=True)
    return path


def fresh_copy(source: Path, dest_dir: Path, name: str) -> Path:
    """Copy source file to a fresh path with no existing tags or timestamp fixes."""
    dest = dest_dir / name
    shutil.copy2(str(source), str(dest))
    # Strip any Keys:CreationDate so timestamp fix always has work to do
    subprocess.run([
        "exiftool", "-overwrite_original", "-Keys:CreationDate=", str(dest)
    ], capture_output=True)
    return dest


def measure_script(cmd_template: list, source: Path, tmp_dir: Path, runs: int = TIMED_RUNS) -> float:
    """
    Measure median wall-clock seconds for a script command across N runs.

    cmd_template: list where the string "__FILE__" will be replaced with each fresh copy path.
    """
    times = []
    for i in range(runs):
        path = fresh_copy(source, tmp_dir, f"run_{i}.mp4")
        cmd = [str(source) if c == "__SOURCE__" else c for c in cmd_template]
        cmd = [str(path) if c == "__FILE__" else c for c in cmd]
        t0 = time.perf_counter()
        subprocess.run(cmd, capture_output=True)
        times.append(time.perf_counter() - t0)
    return statistics.median(times)


def load_baseline() -> dict:
    if BASELINE_FILE.exists():
        return json.loads(BASELINE_FILE.read_text())
    return {}


def save_baseline(results: dict):
    BASELINE_FILE.write_text(json.dumps(results, indent=2) + "\n")


class TestPerformance:
    """Performance snapshot tests for base scripts."""

    @pytest.fixture(autouse=True)
    def tmp(self, tmp_path):
        self._tmp = tmp_path

    def _check(self, name: str, elapsed: float, baseline: dict, results: dict):
        results[name] = round(elapsed, 3)
        if name in baseline:
            base = baseline[name]
            ratio = elapsed / base if base > 0 else 1.0
            delta_pct = (ratio - 1.0) * 100
            if delta_pct > 0:
                status = f"SLOWER +{delta_pct:.0f}% ({elapsed:.2f}s vs baseline {base:.2f}s)"
            else:
                status = f"faster {delta_pct:.0f}% ({elapsed:.2f}s vs baseline {base:.2f}s)"
            print(f"\n  {name}: {status}")
            assert ratio <= (1 + REGRESSION_THRESHOLD), (
                f"{name} regression: {elapsed:.2f}s is {delta_pct:.0f}% slower than baseline {base:.2f}s "
                f"(threshold {REGRESSION_THRESHOLD*100:.0f}%)"
            )
        else:
            print(f"\n  {name}: {elapsed:.2f}s (no baseline yet)")

    def test_tag_media_apply(self, source_mp4):
        """tag-media.py: apply tags + EXIF to a single file."""
        baseline = load_baseline()
        results = {}

        elapsed = measure_script(
            ["python3", str(SCRIPT_DIR / "tag-media.py"),
             "__FILE__",
             "--tags", "gopro,action",
             "--make", "GoPro",
             "--model", "HERO12 Black",
             "--apply"],
            source_mp4, self._tmp
        )
        self._check("tag_media_apply", elapsed, baseline, results)

        if not baseline:
            save_baseline(results)
            print(f"\n  Baseline saved to {BASELINE_FILE}")
        else:
            updated = {**baseline, **results}
            save_baseline(updated)

    def test_fix_media_timestamp_apply(self, source_mp4):
        """fix-media-timestamp.py: apply timestamp fix to a single file."""
        baseline = load_baseline()
        results = {}

        elapsed = measure_script(
            ["python3", str(SCRIPT_DIR / "fix-media-timestamp.py"),
             "__FILE__",
             "--timezone", "+0900",
             "--apply"],
            source_mp4, self._tmp
        )
        self._check("fix_media_timestamp_apply", elapsed, baseline, results)

        if not baseline:
            save_baseline(results)
            print(f"\n  Baseline saved to {BASELINE_FILE}")
        else:
            updated = {**baseline, **results}
            save_baseline(updated)

    def test_tag_media_no_work(self, source_mp4):
        """tag-media.py: file already tagged correctly (check-before-write path)."""
        # Pre-tag the file once
        pre_tagged = fresh_copy(source_mp4, self._tmp, "pre_tagged.mp4")
        subprocess.run([
            "python3", str(SCRIPT_DIR / "tag-media.py"),
            str(pre_tagged),
            "--tags", "gopro",
            "--make", "GoPro",
            "--model", "HERO12 Black",
            "--apply"
        ], capture_output=True, check=True)

        baseline = load_baseline()
        results = {}

        # Now measure the idempotent (no-op) run — still makes reads, skips writes
        times = []
        for _ in range(TIMED_RUNS):
            t0 = time.perf_counter()
            subprocess.run([
                "python3", str(SCRIPT_DIR / "tag-media.py"),
                str(pre_tagged),
                "--tags", "gopro",
                "--make", "GoPro",
                "--model", "HERO12 Black",
                "--apply"
            ], capture_output=True)
            times.append(time.perf_counter() - t0)
        elapsed = statistics.median(times)

        self._check("tag_media_no_work", elapsed, baseline, results)

        if not baseline:
            save_baseline(results)
        else:
            updated = {**baseline, **results}
            save_baseline(updated)
