#!/bin/bash

# Usage:
# ./update_exif_from_filename.sh --timezone +0100 [--apply]

set -e

timezone=""
apply=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --timezone) timezone="$2"; shift 2 ;;
    --apply) apply=1; shift ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

if [[ -z "$timezone" ]]; then
  echo "❌ Error: --timezone is required (e.g. +0100)"
  exit 1
fi

for file in VID_*.mp4 LRV_*.mp4; do
  [[ -f "$file" ]] || continue

  echo "Processing: $file"

  # Extract datetime from filename
  if [[ "$file" =~ ([0-9]{8})_([0-9]{6}) ]]; then
    date_part="${BASH_REMATCH[1]}"
    time_part="${BASH_REMATCH[2]}"
  else
    echo "❌ Skipping: $file (unrecognized format)"
    continue
  fi

  local_dt="${date_part:0:4}:${date_part:4:2}:${date_part:6:2} ${time_part:0:2}:${time_part:2:2}:${time_part:4:2}${timezone}"

  # Convert to UTC
  utc_dt=$(TZ=UTC date -jf "%Y:%m:%d %H:%M:%S%z" "$local_dt" +"%Y:%m:%d %H:%M:%S") || {
    echo "❌ Failed to convert: $local_dt"
    continue
  }

  echo "→ Local: $local_dt"
  echo "→ UTC:   $utc_dt"

  if [[ "$apply" -eq 1 ]]; then
    # Update EXIF
    exiftool -overwrite_original \
      -DateTimeOriginal="$local_dt" \
      -CreateDate="$utc_dt" \
      -MediaCreateDate="$utc_dt" \
      -MediaModifyDate="$utc_dt" \
      "$file"

    # Update file system timestamps
    setfile_date=$(date -j -f "%Y:%m:%d %H:%M:%S" "$utc_dt" +"%m/%d/%Y %H:%M:%S") || {
      echo "❌ Failed to format SetFile date"
      continue
    }

    SetFile -d "$setfile_date" "$file"
    SetFile -m "$setfile_date" "$file"

    echo "✅ Updated timestamps for $file"
  else
    echo "💡  Dry run (use --apply to write)"
  fi

  echo "---"
done
