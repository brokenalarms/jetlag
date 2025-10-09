#!/bin/bash
# fix-video-timestamp-v3.sh
# Bash wrapper for Python implementation
# Maintains compatibility with existing CLI interface while using clean Python implementation

set -euo pipefail

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/fix-media-timestamp.py"

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
# Python will handle path resolution
exec python3 "$PYTHON_SCRIPT" "$@"