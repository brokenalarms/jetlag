#!/bin/bash
# ensure-venv.sh
# Shared helper: creates and activates the Python venv on first run.
# Source this file from Python-wrapping shell scripts — do not run it directly.
#
# If the venv does not exist and requirements.txt is present alongside it,
# the venv is created and dependencies are installed automatically. Output
# goes to stderr so it does not interfere with @@-prefixed machine-readable
# stdout from the calling script.

_ENSURE_VENV_SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_ENSURE_VENV_PATH="$_ENSURE_VENV_SCRIPTS_DIR/media-import"
_ENSURE_VENV_REQS="$_ENSURE_VENV_SCRIPTS_DIR/requirements.txt"

if [[ ! -d "$_ENSURE_VENV_PATH" ]]; then
    if ! command -v python3 &>/dev/null; then
        echo "WARNING: python3 not found — skipping venv setup. Install Python 3 or Xcode Command Line Tools." >&2
    elif [[ -f "$_ENSURE_VENV_REQS" ]]; then
        echo "Setting up Python environment (first run)..." >&2
        python3 -m venv "$_ENSURE_VENV_PATH" >&2
        "$_ENSURE_VENV_PATH/bin/pip" install --quiet -r "$_ENSURE_VENV_REQS" >&2
        echo "Python environment ready." >&2
    fi
fi

if [[ -d "$_ENSURE_VENV_PATH" && -f "$_ENSURE_VENV_PATH/bin/activate" ]]; then
    source "$_ENSURE_VENV_PATH/bin/activate"
fi

unset _ENSURE_VENV_SCRIPTS_DIR _ENSURE_VENV_PATH _ENSURE_VENV_REQS
