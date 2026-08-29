#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PACKAGE_DIR="$SCRIPT_DIR/../../macos/Sources/Tools/jetlag-metadata"
# Optional destination: tests build into a directory of their own so a test run
# does not install a binary the rest of the suite would then pick up.
TARGET="${1:-$SCRIPT_DIR/jetlag-metadata}"

if [ ! -d "$PACKAGE_DIR" ]; then
    echo "error: Swift package not found at $PACKAGE_DIR" >&2
    exit 1
fi

echo "Building jetlag-metadata..."
cd "$PACKAGE_DIR"
swift build -c release 2>&1

BINARY="$PACKAGE_DIR/.build/release/jetlag-metadata"
if [ ! -f "$BINARY" ]; then
    echo "error: build produced no binary at $BINARY" >&2
    exit 1
fi

cp "$BINARY" "$TARGET"
echo "Installed: $TARGET"
