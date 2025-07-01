#!/bin/bash

# normalize_video_timestamps.sh
# Requires: exiftool, SetFile, python3
# Usage: ./normalize_video_timestamps.sh [--apply]

set -euo pipefail
IFS=$'\n\t'

apply=0
if [[ "${1:-}" == "--apply" ]]; then
  apply=1
  shift
fi

fix_colon_tz() {
  # Normalizes timezone offsets +01:00 → +0100 for exiftool
  echo "$1" | sed -E 's/([+-][0-9]{2}):?([0-9]{2})$/\1\2/'
}

parse_filename_datetime() {
  # Expects VID_YYYYMMDD_HHMMSS returns "YYYY:MM:DD HH:MM:SS"
  local file="$1"
  local base
  base="$(basename "$file")"
  if [[ "$base" =~ ^VID_([0-9]{8})_([0-9]{6}) ]]; then
    local d="${BASH_REMATCH[1]}"
    local t="${BASH_REMATCH[2]}"
    echo "${d:0:4}:${d:4:2}:${d:6:2} ${t:0:2}:${t:2:2}:${t:4:2}"
    return 0
  fi
  return 1
}

to_utc() {
  # Usage: to_utc "2025:05:05 11:09:42+0100"
  python3 -c "
import sys
from datetime import datetime, timezone
dt = datetime.strptime('$1', '%Y:%m:%d %H:%M:%S%z')
print(dt.astimezone(timezone.utc).strftime('%Y:%m:%d %H:%M:%S'))
" 2>/dev/null
}

update_metadata() {
  local file="$1"
  local local_time="$2"      # e.g. 2025:05:06 12:07:43+0100
  local utc_time="$3"

  exiftool -overwrite_original \
    "-DateTimeOriginal=$local_time" \
    "-QuickTime:CreateDate=$utc_time" \
    "-QuickTime:ModifyDate=$utc_time" \
    "-FileModifyDate=$utc_time" "$file" >/dev/null 2>&1

  # Strip timezone from local_time for SetFile
  local local_time_no_tz="${local_time:0:19}" # Only the "YYYY:MM:DD HH:MM:SS" part

  SetFile -d "$(date -j -f "%Y:%m:%d %H:%M:%S" "$local_time_no_tz" "+%m/%d/%Y %H:%M:%S")" "$file"
}

print_file_info() {
  local filename="$1"
  local description="$2"
  local local_time="$3"
  local utc_time="$4"
  local cyan="\033[36m"
  local reset="\033[0m"
  # Cyan for filename, rest plain
  printf "${cyan}🔍 %s${reset} [%s]\n" "$filename" "$description"
  printf "⏱️ Local time : %s\n" "$local_time"
  printf "🌐 UTC time   : %s UTC\n\n" "$utc_time"
}

process_file() {
  local file="$1"
  local timezone="$2"
  local tz_source="$3"
  local apply="$4"
  local base
  base="$(basename "$file")"
  local dto
  dto="$(exiftool -s3 -DateTimeOriginal "$file" 2>/dev/null)"
  local media_create
  media_create="$(exiftool -s3 -QuickTime:MediaCreateDate "$file" 2>/dev/null)"

  # *** PRIORITIZE filename+timezone.txt if both present, even if DateTimeOriginal exists ***
  if parse_filename_datetime "$base" >/dev/null && [[ "$tz_source" == "timezone.txt" ]]; then
    local local_dt
    local_dt="$(parse_filename_datetime "$base")"
    local local_time="$local_dt$timezone"
    local utc_time; utc_time="$(to_utc "$local_time")"
    print_file_info "$base" "datetime from VID_ filename, timezone from timezone.txt, TZ=${timezone}" "$local_time" "$utc_time"
    if [[ "$apply" -eq 1 ]]; then
      update_metadata "$file" "$local_time" "$utc_time"
    fi
    return
  fi

  # Method 1: DateTimeOriginal (with TZ)
  if [[ "$tz_source" == "DateTimeOriginal" ]]; then
    local local_time="$dto"
    local utc_time; utc_time="$(to_utc "$local_time")"
    print_file_info "$base" "datetime and zone from DateTimeOriginal, TZ=${local_time:19}" "$local_time" "$utc_time"
    if [[ "$apply" -eq 1 ]]; then
      update_metadata "$file" "$local_time" "$utc_time"
    fi
    return
  fi

  # Method 3: MediaCreateDate + timezone.txt
  if [[ -n "$media_create" && -n "$timezone" ]]; then
    local local_time="$media_create$timezone"
    local utc_time; utc_time="$(to_utc "$local_time")"
    print_file_info "$base" "datetime from MediaCreateDate, timezone from timezone.txt, TZ=${timezone}" "$local_time" "$utc_time"
    if [[ "$apply" -eq 1 ]]; then
      update_metadata "$file" "$local_time" "$utc_time"
    fi
    return
  fi

  echo "❌ $base: No valid DateTimeOriginal, filename, or MediaCreateDate. Skipping." >&2
}

echo "🕓 Scanning video files..."

find . -type d | while read -r dir; do
  files=()
  while IFS= read -r -d '' file; do
    files+=("$file")
  done < <(find "$dir" -maxdepth 1 -type f \( -iname '*.mp4' -o -iname '*.mov' \) -print0)
  [[ ${#files[@]} -eq 0 ]] && continue

  for file in "${files[@]}"; do
    base="$(basename "$file")"
    dto="$(exiftool -s3 -DateTimeOriginal "$file" 2>/dev/null)"

    # *** Patch: always use filename+timezone.txt if filename matches and file present ***
    if parse_filename_datetime "$base" >/dev/null && [[ -f "$dir/timezone.txt" ]]; then
      timezone=$(fix_colon_tz "$(head -n1 "$dir/timezone.txt")")
      tz_source="timezone.txt"
    elif [[ "$dto" =~ [+-][0-9]{2}(:?[0-9]{2})$ ]]; then
      timezone="${dto:19}"
      tz_source="DateTimeOriginal"
    elif [[ -f "$dir/timezone.txt" ]]; then
      chflags hidden "$dir/timezone.txt"
      timezone=$(fix_colon_tz "$(head -n1 "$dir/timezone.txt")")
      tz_source="timezone.txt"
    else
      echo "❌ $file: No timezone found in DateTimeOriginal or timezone.txt, aborting."
      exit 1
    fi

    process_file "$file" "$timezone" "$tz_source" "$apply"
  done
done
