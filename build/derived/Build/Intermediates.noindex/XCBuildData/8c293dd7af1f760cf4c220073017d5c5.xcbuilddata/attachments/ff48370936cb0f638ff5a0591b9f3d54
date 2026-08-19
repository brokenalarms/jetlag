#!/bin/sh
set -e
DEST="${BUILT_PRODUCTS_DIR}/${PRODUCT_NAME}.app/Contents/Resources/scripts"
rm -rf "$DEST"
cp -r "${SRCROOT}/../scripts/" "$DEST"
# A checkout's .venv holds absolute paths into the checkout — the bundle
# imports from site-packages below instead.
rm -rf "$DEST/.venv"
find "$DEST" -name __pycache__ -type d -prune -exec rm -rf {} +
# Vendor dependencies with the same interpreter the app runs them on
# (lib/ensure-venv.sh resolves to /usr/bin/python3) — PyYAML ships a C
# extension, so wheels built for another version fail to import.
# pip resolution takes ~30-60s per build; cache the installed tree in
# DerivedData keyed by the requirements hash and copy it in instead.
rm -rf "$DEST/site-packages"
REQ_HASH=$(shasum "$DEST/requirements.txt" | awk '{print $1}')
PIP_CACHE="${BUILT_PRODUCTS_DIR}/jetlag-site-packages-cache"
if [ ! -f "$PIP_CACHE/.stamp" ] || [ "$(cat "$PIP_CACHE/.stamp")" != "$REQ_HASH" ]; then
  rm -rf "$PIP_CACHE"
  /usr/bin/python3 -m pip install --quiet --target "$PIP_CACHE" -r "$DEST/requirements.txt"
  echo "$REQ_HASH" > "$PIP_CACHE/.stamp"
fi
cp -R "$PIP_CACHE" "$DEST/site-packages"
rm -f "$DEST/site-packages/.stamp"

# Build jetlag-metadata Swift CLI and install into bundle
METADATA_PKG="${SRCROOT}/Sources/Tools/jetlag-metadata"
if [ -d "$METADATA_PKG" ]; then
  swift build -c release --package-path "$METADATA_PKG" 2>&1
  cp "$METADATA_PKG/.build/release/jetlag-metadata" "$DEST/tools/jetlag-metadata"
fi

# Verify vendored tools are present (copied by cp -r above)
for tool in exiftool tag ffprobe jetlag-metadata; do
  if [ ! -f "$DEST/tools/$tool" ]; then
    echo "error: scripts/tools/$tool missing — run scripts/tools/download-${tool}.sh or scripts/tools/build-jetlag-metadata.sh or see scripts/tools/README" >&2
    exit 1
  fi
done
# Gyroflow is optional: the pipeline skips stabilization gracefully when
# absent, and the app gates gyroflow features on its presence.
if [ ! -f "$DEST/tools/gyroflow" ]; then
  echo "note: scripts/tools/gyroflow not bundled — gyroflow features disabled in this build" >&2
fi

