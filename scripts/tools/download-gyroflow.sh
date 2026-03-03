#!/bin/bash
# Download or extract the Gyroflow CLI binary for macOS.
# Places the binary at scripts/tools/gyroflow.
#
# The Gyroflow app binary doubles as a CLI: it accepts --export-project flags
# for headless .gyroflow project generation.
#
# Source priority:
#   1. Copy from /Applications/Gyroflow.app (already installed)
#   2. Copy from Homebrew (brew install gyroflow)
#   3. Download from GitHub releases (macOS universal .dmg)
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="$SCRIPT_DIR/gyroflow"

if [ -f "$OUT" ]; then
    echo "gyroflow already exists at $OUT"
    "$OUT" --help 2>/dev/null | head -1 || true
    exit 0
fi

if [ "$(uname -s)" != "Darwin" ]; then
    echo "Gyroflow bundling is macOS-only (the app is a macOS binary)" >&2
    exit 1
fi

# 1. Try /Applications/Gyroflow.app
APP_BINARY="/Applications/Gyroflow.app/Contents/MacOS/gyroflow"
if [ -f "$APP_BINARY" ]; then
    echo "Copying from installed Gyroflow.app..."
    cp "$APP_BINARY" "$OUT"
    chmod +x "$OUT"
    echo "Installed: $OUT"
    exit 0
fi

# 2. Try Homebrew
BREW_BINARY="$(brew --prefix 2>/dev/null)/bin/gyroflow" || true
if [ -f "$BREW_BINARY" ]; then
    echo "Copying from Homebrew..."
    cp "$BREW_BINARY" "$OUT"
    chmod +x "$OUT"
    echo "Installed: $OUT"
    exit 0
fi

# 3. Download from GitHub releases
VERSION="1.5.4"
DMG_URL="https://github.com/gyroflow/gyroflow/releases/download/v${VERSION}/Gyroflow-mac-universal.dmg"
TMPDIR_DL="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_DL"; hdiutil detach "$TMPDIR_DL/mount" 2>/dev/null || true' EXIT

echo "Downloading Gyroflow v${VERSION} from GitHub..."
curl -L -o "$TMPDIR_DL/Gyroflow.dmg" "$DMG_URL"

echo "Mounting DMG..."
mkdir -p "$TMPDIR_DL/mount"
hdiutil attach "$TMPDIR_DL/Gyroflow.dmg" -mountpoint "$TMPDIR_DL/mount" -nobrowse -quiet

DMG_APP="$TMPDIR_DL/mount/Gyroflow.app/Contents/MacOS/gyroflow"
if [ ! -f "$DMG_APP" ]; then
    echo "ERROR: Could not find gyroflow binary in DMG" >&2
    ls -la "$TMPDIR_DL/mount/" >&2
    exit 1
fi

cp "$DMG_APP" "$OUT"
chmod +x "$OUT"

echo "Installed: $OUT"
"$OUT" --help 2>/dev/null | head -1 || true
