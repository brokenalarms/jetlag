#!/bin/bash

# Usage: ./update_exif_from_filename.sh [--apply]

apply_changes=0
match_count=0

if [[ "$1" == "--apply" ]]; then
  apply_changes=1
fi

mkdir -p corrected

echo "---------------------------------------------------"
echo "EXIF correction for .mp4 files based on filename"
echo "Mode: $([[ "$apply_changes" -eq 1 ]] && echo APPLYING || echo DRY RUN)"
echo "---------------------------------------------------"

for file in VID_*.mp4; do
  [[ -f "$file" ]] || continue

  # Match pattern with optional suffix like (2)
  if [[ "$file" =~ ^VID_([0-9]{8})_([0-9]{6})_00_([0-9]+) ]]; then
    date_part="${BASH_REMATCH[1]}"
    time_part="${BASH_REMATCH[2]}"
    sequence="${BASH_REMATCH[3]}"
    exif_datetime="${date_part:0:4}:${date_part:4:2}:${date_part:6:2} ${time_part:0:2}:${time_part:2:2}:${time_part:4:2}"
    touch_time="${date_part}${time_part}"
    dest_path="corrected/$file"

    echo "Checking: $file"
    echo " → EXIF datetime: $exif_datetime"
    echo " → Target:        $dest_path"

    if [[ "$apply_changes" -eq 1 ]]; then
      cp "$file" "$dest_path"
      exiftool -overwrite_original \
        "-CreateDate=$exif_datetime" \
        "-MediaCreateDate=$exif_datetime" \
        "-ModifyDate=$exif_datetime" "$dest_path" >/dev/null
      touch -t "${touch_time}" "$dest_path"
    else
      echo "Would copy to: $dest_path"
      echo "Would set EXIF CreateDate, MediaCreateDate, and ModifyDate to: $exif_datetime"
      echo "Would set mod time via touch to: $touch_time"
    fi

    echo "---"
    match_count=$((match_count + 1))
  fi
done

echo "✅ Total files matched and processed: $match_count"
