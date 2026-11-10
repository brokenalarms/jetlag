#!/bin/bash
# launch.sh
# The body every <command>.sh shares. A command's wrapper sources this file with
# the name of its entry point in cli/ and its own arguments — do not run it directly:
#
#   source "$(dirname "${BASH_SOURCE[0]}")/lib/launch.sh" media_pipeline "$@"
#
# Resolves the interpreter (ensure-venv.sh), puts scripts/ on PYTHONPATH so the
# entry point imports cli.* and lib.* wherever it is run from, then replaces the
# shell with Python, so the command's exit status and signals are Python's own.

set -euo pipefail

_LAUNCH_SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_LAUNCH_ENTRY="$_LAUNCH_SCRIPTS_DIR/cli/$1.py"
shift

source "$_LAUNCH_SCRIPTS_DIR/lib/ensure-venv.sh"

if [[ ! -f "$_LAUNCH_ENTRY" ]]; then
    echo "ERROR: Python implementation not found at $_LAUNCH_ENTRY" >&2
    exit 1
fi

export PYTHONPATH="$_LAUNCH_SCRIPTS_DIR${PYTHONPATH:+:$PYTHONPATH}"
exec "$JETLAG_PYTHON" "$_LAUNCH_ENTRY" "$@"
