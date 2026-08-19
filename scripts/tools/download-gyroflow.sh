#!/bin/bash
# Install Gyroflow as an optional companion app, and report where it lives.
#
# Gyroflow ships as a full macOS .app. Its CLI (Contents/MacOS/gyroflow, which
# accepts --export-project for headless .gyroflow project generation) only runs
# from inside that bundle: extracted on its own it has an invalid code
# signature and is missing the mdk/Qt frameworks it links against. So the whole
# .app is installed, into
#
#     ~/Library/Application Support/Jetlag/tools/Gyroflow.app
#
# never inside Jetlag.app itself — writing into the signed bundle would break
# its signature.
#
# Resolution order (an existing install is reported, never re-downloaded):
#   1. /Applications/Gyroflow.app
#   2. the Application Support tools directory above
#   3. gyroflow on $PATH
#   4. --configured PATH
#
# Usage: download-gyroflow.sh [--check] [--configured PATH]
#   --check   report presence only; never download or write anything
#
# Presence is reported on stdout as machine-readable data:
#   @@present=true|false
#   @@path=/resolved/path/to/gyroflow      (only when present)
#   @@source=applications|jetlag-tools|path|configured  (only when present)
set -e

VERSION="1.5.4"
DMG_URL="https://github.com/gyroflow/gyroflow/releases/download/v${VERSION}/Gyroflow-mac-universal.dmg"

APPLICATIONS_DIR="${JETLAG_APPLICATIONS_DIR:-/Applications}"
TOOLS_DIR="${JETLAG_TOOLS_DIR:-$HOME/Library/Application Support/Jetlag/tools}"

CHECK_ONLY=false
CONFIGURED=""
while [ $# -gt 0 ]; do
    case "$1" in
        --check) CHECK_ONLY=true; shift ;;
        --configured) CONFIGURED="$2"; shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done

app_binary() {
    # Echo the CLI inside "$1/Gyroflow.app" when it is executable.
    local binary="$1/Gyroflow.app/Contents/MacOS/gyroflow"
    if [ -x "$binary" ]; then
        echo "$binary"
    fi
}

report_present() {
    echo "@@present=true"
    echo "@@path=$1"
    echo "@@source=$2"
}

resolve() {
    local found
    found="$(app_binary "$APPLICATIONS_DIR")"
    if [ -n "$found" ]; then
        report_present "$found" applications
        return 0
    fi
    found="$(app_binary "$TOOLS_DIR")"
    if [ -n "$found" ]; then
        report_present "$found" jetlag-tools
        return 0
    fi
    found="$(command -v gyroflow || true)"
    if [ -n "$found" ]; then
        report_present "$found" path
        return 0
    fi
    if [ -n "$CONFIGURED" ] && [ -x "$CONFIGURED" ]; then
        report_present "$CONFIGURED" configured
        return 0
    fi
    return 1
}

if resolve; then
    exit 0
fi

if [ "$CHECK_ONLY" = true ]; then
    echo "@@present=false"
    exit 0
fi

if [ "$(uname -s)" != "Darwin" ]; then
    echo "@@present=false"
    echo "Gyroflow is a macOS app and cannot be installed here" >&2
    exit 1
fi

TMPDIR_DL="$(mktemp -d)"
MOUNT="$TMPDIR_DL/mount"
trap 'hdiutil detach "$MOUNT" -quiet 2>/dev/null || true; rm -rf "$TMPDIR_DL"' EXIT

echo "Downloading Gyroflow v${VERSION}..." >&2
curl -fL --progress-bar -o "$TMPDIR_DL/Gyroflow.dmg" "$DMG_URL" >&2

echo "Mounting disk image..." >&2
mkdir -p "$MOUNT"
hdiutil attach "$TMPDIR_DL/Gyroflow.dmg" -mountpoint "$MOUNT" -nobrowse -quiet

if [ ! -d "$MOUNT/Gyroflow.app" ]; then
    echo "ERROR: no Gyroflow.app inside the downloaded disk image" >&2
    ls -la "$MOUNT" >&2
    echo "@@present=false"
    exit 1
fi

echo "Installing into $TOOLS_DIR..." >&2
mkdir -p "$TOOLS_DIR"
rm -rf "$TOOLS_DIR/Gyroflow.app"
cp -R "$MOUNT/Gyroflow.app" "$TOOLS_DIR/Gyroflow.app"

INSTALLED="$(app_binary "$TOOLS_DIR")"
if [ -z "$INSTALLED" ]; then
    echo "ERROR: installed Gyroflow.app has no runnable CLI" >&2
    echo "@@present=false"
    exit 1
fi

echo "Installed: $TOOLS_DIR/Gyroflow.app" >&2
report_present "$INSTALLED" jetlag-tools
