#!/usr/bin/env python3
"""
Test runner for media scripts
Runs all tests with appropriate configuration
"""

import sys
import subprocess
from pathlib import Path

def main():
    """Run all tests"""
    script_dir = Path(__file__).parent
    tests_dir = script_dir / "scripts" / "tests"

    # Check if pytest is available
    try:
        import pytest
    except ImportError:
        print("Error: pytest not found. Install with:", file=sys.stderr)
        print("  pip install -r scripts/tests/requirements.txt", file=sys.stderr)
        return 1

    # Run pytest
    args = [
        str(tests_dir),
        "-v",  # Verbose
        "--tb=short",  # Shorter traceback format
        "--color=yes",  # Colored output
    ]

    # Add any command-line arguments passed to this script
    args.extend(sys.argv[1:])

    print(f"Running tests in {tests_dir}", file=sys.stderr)
    print(f"Arguments: {' '.join(args)}", file=sys.stderr)
    print(file=sys.stderr)

    return pytest.main(args)

if __name__ == "__main__":
    sys.exit(main())
