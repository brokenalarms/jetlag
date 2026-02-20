#!/bin/bash
# generate-gyroflow.sh
# Bash wrapper for Python implementation

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/generate-gyroflow.py"

# Activate venv if it exists
VENV="$SCRIPT_DIR/media-import"
if [[ -d "$VENV" && -f "$VENV/bin/activate" ]]; then
    source "$VENV/bin/activate"
fi

# Check if Python script exists
if [[ ! -f "$PYTHON_SCRIPT" ]]; then
    echo "ERROR: Python implementation not found at $PYTHON_SCRIPT" >&2
    exit 1
fi

# Pass all arguments directly to Python implementation
exec python3 "$PYTHON_SCRIPT" "$@"
