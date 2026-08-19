#!/bin/bash
# Download a static ffprobe binary for macOS (universal) or Linux (x86_64).
# Places the binary at scripts/tools/ffprobe.
#
# Source: evermeet.cx (macOS), johnvansickle.com (Linux)
# These are widely-used static FFmpeg builds that include ffprobe.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="$SCRIPT_DIR/ffprobe"

if [ -f "$OUT" ]; then
    echo "ffprobe already exists at $OUT"
    "$OUT" -version 2>/dev/null | head -1 || true
    exit 0
fi

OS="$(uname -s)"
ARCH="$(uname -m)"
TMPDIR_DL="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_DL"' EXIT

case "$OS" in
    Darwin)
        # evermeet.cx provides macOS static builds (x86_64 + arm64 universal)
        URL="https://evermeet.cx/ffmpeg/ffprobe-7.1.1.zip"
        echo "Downloading ffprobe for macOS from evermeet.cx..."
        curl -L -o "$TMPDIR_DL/ffprobe.zip" "$URL"
        unzip -o "$TMPDIR_DL/ffprobe.zip" -d "$TMPDIR_DL"
        mv "$TMPDIR_DL/ffprobe" "$OUT"
        ;;
    Linux)
        # johnvansickle.com provides static Linux builds
        URL="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
        echo "Downloading ffprobe for Linux (amd64) from johnvansickle.com..."
        curl -L -o "$TMPDIR_DL/ffmpeg.tar.xz" "$URL"
        tar xf "$TMPDIR_DL/ffmpeg.tar.xz" -C "$TMPDIR_DL" --wildcards '*/ffprobe' --strip-components=1
        mv "$TMPDIR_DL/ffprobe" "$OUT"
        ;;
    *)
        echo "Unsupported OS: $OS" >&2
        exit 1
        ;;
esac

chmod +x "$OUT"
echo "Installed: $OUT"
"$OUT" -version 2>/dev/null | head -1 || true
