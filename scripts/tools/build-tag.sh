#!/bin/bash
# Build the 'tag' binary from vendored source (macOS only).
# Run once after cloning: scripts/tools/build-tag.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="$SCRIPT_DIR/tag-src"
OUT="$SCRIPT_DIR/tag"

if [ "$(uname)" != "Darwin" ]; then
    echo "tag can only be built on macOS" >&2
    exit 1
fi

echo "Building tag from $SRC..."
cc -O2 "$SRC/main.m" "$SRC/Tag.m" "$SRC/TagName.m" \
    -framework Foundation -framework CoreServices \
    -o "$OUT"

echo "Built: $OUT"
"$OUT" --version 2>/dev/null || "$OUT" --help 2>/dev/null | head -1 || true
