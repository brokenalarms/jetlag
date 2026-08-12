#!/bin/bash
# ensure-venv.sh
# Shared helper: resolves the Python interpreter and makes dependencies importable.
# Source this file from Python-wrapping shell scripts — do not run it directly.
#
# Exports JETLAG_PYTHON, the interpreter every wrapper execs. Resolving it here
# rather than relying on whichever python3 PATH happens to offer keeps the app,
# the terminal and Xcode on the same interpreter — Xcode puts its own Python 3.9
# framework ahead of Homebrew, so an unpinned `python3` differs by launch context.
#
# Dependencies come from one of two places:
#   site-packages/ — vendored into the app bundle at build time
#   .venv/         — created on first run in a checkout
#
# Output goes to stderr so it does not interfere with @@-prefixed machine-readable
# stdout from the calling script.

_ENSURE_VENV_SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_ENSURE_VENV_DIR="$_ENSURE_VENV_SCRIPTS_DIR/.venv"
_ENSURE_VENV_REQS="$_ENSURE_VENV_SCRIPTS_DIR/requirements.txt"
_ENSURE_VENV_TOOLS="$_ENSURE_VENV_SCRIPTS_DIR/tools"
_ENSURE_VENV_VENDORED="$_ENSURE_VENV_SCRIPTS_DIR/site-packages"

# Floor is the Python macOS ships, so a user installs nothing to run the app.
_ENSURE_VENV_MIN_MAJOR=3
_ENSURE_VENV_MIN_MINOR=9

# Prepend vendored tools (ffprobe, gyroflow, exiftool, tag) to PATH
if [[ -d "$_ENSURE_VENV_TOOLS" ]]; then
    export PATH="$_ENSURE_VENV_TOOLS:$PATH"
fi

_ensure_venv_python_ok() {
    [[ -x "$1" ]] || return 1
    "$1" -c "import sys; sys.exit(0 if sys.version_info[:2] >= (${_ENSURE_VENV_MIN_MAJOR}, ${_ENSURE_VENV_MIN_MINOR}) else 1)" 2>/dev/null
}

_ensure_venv_find_python() {
    if [[ -n "${JETLAG_PYTHON:-}" ]] && _ensure_venv_python_ok "$JETLAG_PYTHON"; then
        echo "$JETLAG_PYTHON"
        return 0
    fi
    if _ensure_venv_python_ok /usr/bin/python3; then
        echo /usr/bin/python3
        return 0
    fi
    local from_path
    from_path="$(command -v python3 2>/dev/null)"
    if [[ -n "$from_path" ]] && _ensure_venv_python_ok "$from_path"; then
        echo "$from_path"
        return 0
    fi
    return 1
}

if ! _ENSURE_VENV_BASE_PYTHON="$(_ensure_venv_find_python)"; then
    echo "ERROR: no Python ${_ENSURE_VENV_MIN_MAJOR}.${_ENSURE_VENV_MIN_MINOR}+ found. Install Xcode Command Line Tools (xcode-select --install), or set JETLAG_PYTHON to an interpreter." >&2
    exit 1
fi

if [[ -d "$_ENSURE_VENV_VENDORED" ]]; then
    # Bundled app: dependencies ship alongside the scripts, no venv to build.
    export PYTHONPATH="$_ENSURE_VENV_VENDORED${PYTHONPATH:+:$PYTHONPATH}"
    export JETLAG_PYTHON="$_ENSURE_VENV_BASE_PYTHON"
else
    if [[ -d "$_ENSURE_VENV_DIR" ]] && ! _ensure_venv_python_ok "$_ENSURE_VENV_DIR/bin/python3"; then
        echo "Rebuilding .venv — its interpreter is missing or below ${_ENSURE_VENV_MIN_MAJOR}.${_ENSURE_VENV_MIN_MINOR}..." >&2
        rm -rf "$_ENSURE_VENV_DIR"
    fi

    if [[ ! -d "$_ENSURE_VENV_DIR" && -f "$_ENSURE_VENV_REQS" ]]; then
        echo "Setting up Python dependencies (first run)..." >&2
        "$_ENSURE_VENV_BASE_PYTHON" -m venv "$_ENSURE_VENV_DIR" >&2
        "$_ENSURE_VENV_DIR/bin/pip" install --quiet -r "$_ENSURE_VENV_REQS" >&2
        echo "Python dependencies ready." >&2
    fi

    if [[ -d "$_ENSURE_VENV_DIR" ]]; then
        export PATH="$_ENSURE_VENV_DIR/bin:$PATH"
        export JETLAG_PYTHON="$_ENSURE_VENV_DIR/bin/python3"
    else
        export JETLAG_PYTHON="$_ENSURE_VENV_BASE_PYTHON"
    fi
fi

unset _ENSURE_VENV_SCRIPTS_DIR _ENSURE_VENV_DIR _ENSURE_VENV_REQS _ENSURE_VENV_TOOLS \
      _ENSURE_VENV_VENDORED _ENSURE_VENV_BASE_PYTHON \
      _ENSURE_VENV_MIN_MAJOR _ENSURE_VENV_MIN_MINOR
unset -f _ensure_venv_python_ok _ensure_venv_find_python
