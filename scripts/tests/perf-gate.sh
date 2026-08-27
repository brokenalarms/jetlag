#!/bin/bash
# Local performance gate: the same comparison ci.yml runs, for use in a worktree or
# on a dev machine.
#
# Checks out origin/main's scripts into a temporary tree, then runs
# test_performance.py once with both trees available so it can interleave
# baseline and candidate runs (A B A B A B) and compare medians — a runner
# slowdown mid-run then drags both sides down together instead of only
# whichever block happened to run during the slow window. Exit status is the
# comparison's: see REGRESSION_THRESHOLD in test_performance.py and
# docs/testing.md for how the threshold was measured.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON="${JETLAG_PYTHON:-$SCRIPT_DIR/.venv/bin/python}"
BASE_TREE="$(mktemp -d -t perf_base)"
trap 'rm -rf "$BASE_TREE"' EXIT

git -C "$REPO_ROOT" fetch -q origin main
git -C "$REPO_ROOT" archive origin/main scripts | tar -x -C "$BASE_TREE"
# The baseline scripts run with the working tree's vendored tools and interpreter:
# lib/ensure-venv.sh honours JETLAG_PYTHON, so the temporary tree never creates a
# venv of its own.
ln -s "$SCRIPT_DIR/tools" "$BASE_TREE/scripts/tools" 2>/dev/null || true
export JETLAG_PYTHON="$PYTHON"

echo "→ comparing working tree against origin/main, interleaved"
cd "$SCRIPT_DIR"
"$PYTHON" -m pytest tests/test_performance.py -q -p no:cacheprovider -s \
    --perf-baseline-scripts-dir="$BASE_TREE/scripts" --perf-results-file="$(mktemp -t perf_results).json"
