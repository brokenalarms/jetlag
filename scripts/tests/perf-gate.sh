#!/bin/bash
# Local performance gate: the same comparison ci.yml runs, for use in a worktree or
# on a dev machine where no baseline exists.
#
# tests/perf_baseline.json is machine-specific and gitignored, so a fresh checkout
# has nothing to compare against and test_performance.py passes on "no baseline".
# This script records the baseline from origin/main's scripts in a temporary
# checkout, then runs the comparison against the working tree. Exit status is the
# comparison's: a >5% regression fails.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON="${JETLAG_PYTHON:-$SCRIPT_DIR/.venv/bin/python}"
BASELINE="$(mktemp -t perf_baseline).json"
BASE_TREE="$(mktemp -d -t perf_base)"
trap 'rm -rf "$BASE_TREE" "$BASELINE"' EXIT

git -C "$REPO_ROOT" fetch -q origin main
git -C "$REPO_ROOT" archive origin/main scripts | tar -x -C "$BASE_TREE"
# The baseline scripts run with the working tree's vendored tools and interpreter:
# lib/ensure-venv.sh honours JETLAG_PYTHON, so the temporary tree never creates a
# venv of its own.
ln -s "$SCRIPT_DIR/tools" "$BASE_TREE/scripts/tools" 2>/dev/null || true
export JETLAG_PYTHON="$PYTHON"

echo "→ recording baseline from origin/main"
(cd "$BASE_TREE/scripts" && "$PYTHON" -m pytest tests/test_performance.py -q -p no:cacheprovider \
    --perf-baseline --perf-baseline-file "$BASELINE" -s | tail -5)

echo "→ comparing working tree against it"
cd "$SCRIPT_DIR"
"$PYTHON" -m pytest tests/test_performance.py -q -p no:cacheprovider -s \
    --perf-baseline-file "$BASELINE" --perf-results-file "$(mktemp -t perf_results).json"
