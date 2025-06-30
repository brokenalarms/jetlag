#!/bin/bash

shopt -s nullglob
for f in ./*.MP4; do
  echo "▶ Processing: $f"

  # Extract full DateTimeOriginal (with timezone)
  original=$(exiftool -s3 -DateTimeOriginal "$f")
  if [[ -z "$original" ]]; then
    echo "❌ Skipping $f (no DateTimeOriginal)"
    continue
  fi

  # Strip offset for SetFile compatibility (SetFile doesn't handle timezone)
  timestamp=$(echo "$original" | sed 's/[\+\-][0-9:]*//')

  # Convert to macOS SetFile format
  macos_time=$(date -j -f "%Y:%m:%d %H:%M:%S" "$timestamp" +"%m/%d/%Y %H:%M:%S")

  # Update metadata timestamps
  exiftool \
    "-MediaCreateDate=$original" \
    "-CreateDate=$original" \
    "-ModifyDate=$original" \
    -overwrite_original "$f"

  # Update filesystem timestamps
  xcrun SetFile -d "$macos_time" -m "$macos_time" "$f"

  echo "✅ Updated: $f"
done
