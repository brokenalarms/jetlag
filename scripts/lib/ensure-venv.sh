#!/bin/bash
# ensure-venv.sh
# Shared helper: ensures Python dependencies are available via a local venv.
# Source this file from Python-wrapping shell scripts — do not run it directly.
#
# On first run, creates .venv/ and installs requirements.txt.
# Prepends .venv/bin to PATH so python3 and other entry points resolve to the venv.
# Output goes to stderr so it does not interfere with @@-prefixed machine-readable
# stdout from the calling script.

_ENSURE_VENV_SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_ENSURE_VENV_DIR="$_ENSURE_VENV_SCRIPTS_DIR/.venv"
_ENSURE_VENV_REQS="$_ENSURE_VENV_SCRIPTS_DIR/requirements.txt"
_ENSURE_VENV_TOOLS="$_ENSURE_VENV_SCRIPTS_DIR/tools"

# Prepend vendored tools (ffprobe, gyroflow, exiftool, tag) to PATH
if [[ -d "$_ENSURE_VENV_TOOLS" ]]; then
    export PATH="$_ENSURE_VENV_TOOLS:$PATH"
fi

if [[ ! -d "$_ENSURE_VENV_DIR" ]]; then
    if ! command -v python3 &>/dev/null; then
        echo "WARNING: python3 not found — skipping venv setup. Install Python 3 or Xcode Command Line Tools." >&2
    elif [[ -f "$_ENSURE_VENV_REQS" ]]; then
        echo "Setting up Python dependencies (first run)..." >&2
        python3 -m venv "$_ENSURE_VENV_DIR" >&2
        "$_ENSURE_VENV_DIR/bin/pip" install --quiet -r "$_ENSURE_VENV_REQS" >&2
        echo "Python dependencies ready." >&2
    fi
fi

if [[ -d "$_ENSURE_VENV_DIR" ]]; then
    export PATH="$_ENSURE_VENV_DIR/bin:$PATH"
fi

unset _ENSURE_VENV_SCRIPTS_DIR _ENSURE_VENV_DIR _ENSURE_VENV_REQS _ENSURE_VENV_TOOLS
