#!/bin/bash
# ensure-venv.sh
# Shared helper: ensures Python dependencies are available via PYTHONPATH.
# Source this file from Python-wrapping shell scripts — do not run it directly.
#
# On first run, installs requirements.txt into a local site-packages/ directory.
# Sets PYTHONPATH so Python can find the packages without venv activation —
# nothing is left behind in the user's shell environment after the subprocess exits.
# Output goes to stderr so it does not interfere with @@-prefixed machine-readable
# stdout from the calling script.

_ENSURE_DEPS_SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_ENSURE_DEPS_SITE_PACKAGES="$_ENSURE_DEPS_SCRIPTS_DIR/site-packages"
_ENSURE_DEPS_REQS="$_ENSURE_DEPS_SCRIPTS_DIR/requirements.txt"

if [[ ! -d "$_ENSURE_DEPS_SITE_PACKAGES" ]]; then
    if ! command -v python3 &>/dev/null; then
        echo "WARNING: python3 not found — skipping dependency setup. Install Python 3 or Xcode Command Line Tools." >&2
    elif [[ -f "$_ENSURE_DEPS_REQS" ]]; then
        echo "Setting up Python dependencies (first run)..." >&2
        python3 -m pip install --quiet --target "$_ENSURE_DEPS_SITE_PACKAGES" -r "$_ENSURE_DEPS_REQS" >&2
        echo "Python dependencies ready." >&2
    fi
fi

if [[ -d "$_ENSURE_DEPS_SITE_PACKAGES" ]]; then
    export PYTHONPATH="$_ENSURE_DEPS_SITE_PACKAGES${PYTHONPATH:+:$PYTHONPATH}"
fi

unset _ENSURE_DEPS_SCRIPTS_DIR _ENSURE_DEPS_SITE_PACKAGES _ENSURE_DEPS_REQS
