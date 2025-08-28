#!/usr/bin/env bash
# run-all-tests.sh
# Runs all test suites for video processing scripts

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Make test scripts executable
chmod +x "$SCRIPT_DIR/test-fix-video-timestamp.sh"
chmod +x "$SCRIPT_DIR/test-organize-by-date.sh"

echo "Running all video processing tests..."
echo "====================================="
echo

# Track overall results
total_passed=0
total_failed=0

# Run fix-video-timestamp tests
echo "🔧 Running fix-video-timestamp tests..."
if "$SCRIPT_DIR/test-fix-video-timestamp.sh"; then
    echo "✅ fix-video-timestamp tests passed"
    total_passed=$((total_passed + 1))
else
    echo "❌ fix-video-timestamp tests failed"
    total_failed=$((total_failed + 1))
fi

echo
echo "📁 Running organize-by-date tests..."
if "$SCRIPT_DIR/test-organize-by-date.sh"; then
    echo "✅ organize-by-date tests passed"
    total_passed=$((total_passed + 1))
else
    echo "❌ organize-by-date tests failed" 
    total_failed=$((total_failed + 1))
fi

echo
echo "====================================="
echo "Overall Test Results:"
echo "  Suites passed: $total_passed"
echo "  Suites failed: $total_failed"

if [[ $total_failed -eq 0 ]]; then
    echo "🎉 All test suites passed!"
    exit 0
else
    echo "💥 Some test suites failed!"
    exit 1
fi