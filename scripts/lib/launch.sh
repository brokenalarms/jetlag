#!/bin/bash
# launch.sh
# The body every <command>.sh shares. A command's wrapper sources this file with
# the command's Python entry point and its own arguments — do not run it directly:
#
#   source "$(dirname "${BASH_SOURCE[0]}")/lib/launch.sh" media-pipeline.py "$@"
#
# Resolves the interpreter (ensure-venv.sh), then replaces the shell with Python,
# so the command's exit status and signals are Python's own.

set -euo pipefail

_LAUNCH_SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_LAUNCH_ENTRY="$_LAUNCH_SCRIPTS_DIR/$1"
shift

source "$_LAUNCH_SCRIPTS_DIR/lib/ensure-venv.sh"

if [[ ! -f "$_LAUNCH_ENTRY" ]]; then
    echo "ERROR: Python implementation not found at $_LAUNCH_ENTRY" >&2
    exit 1
fi

exec "$JETLAG_PYTHON" "$_LAUNCH_ENTRY" "$@"
