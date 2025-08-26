#!/bin/bash
# Library - Timestamp fixing functions for video files
# Not executable directly - source this file from other scripts

# CSV-based timezone lookup
get_timezone_for_country() {
  local input="$1"
  local country_code=""
  local SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local TIMEZONE_DIR="$SCRIPT_DIR/timezones"
  local country_csv="$TIMEZONE_DIR/country.csv"
  local timezone_csv="$TIMEZONE_DIR/time_zone.csv"
  
  # Check if CSV files exist
  [[ -f "$country_csv" ]] || { echo "ERROR: $country_csv not found" >&2; return 1; }
  [[ -f "$timezone_csv" ]] || { echo "ERROR: $timezone_csv not found" >&2; return 1; }
  
  # Step 1: Resolve input to country code
  if [[ ${#input} -eq 2 ]]; then
    # Input is likely a country code, verify it exists
    country_code="$(echo "$input" | tr '[:lower:]' '[:upper:]')"
    if ! grep -q "^$country_code," "$country_csv"; then
      return 1  # Invalid country code
    fi
  else
    # Input is country name, find the code
    country_code="$(grep -i ",$input$" "$country_csv" | cut -d',' -f1)"
    [[ -n "$country_code" ]] || return 1  # Country not found
  fi
  
  # Step 2: Find current timezone for country code
  # Get the most recent timezone entry for this country
  local timezone_line="$(grep ",$country_code," "$timezone_csv" | tail -1)"
  [[ -n "$timezone_line" ]] || return 1  # No timezone data for country
  
  # Step 3: Extract offset and convert to +HHMM format
  local offset_seconds="$(echo "$timezone_line" | cut -d',' -f5)"
  
  # Convert seconds to +HHMM format
  if [[ "$offset_seconds" -eq 0 ]]; then
    echo "+0000"
  else
    local abs_seconds=$((offset_seconds < 0 ? -offset_seconds : offset_seconds))
    local hours=$((abs_seconds / 3600))
    local minutes=$(((abs_seconds % 3600) / 60))
    local sign=$([[ offset_seconds -lt 0 ]] && echo "-" || echo "+")
    printf "%s%02d%02d" "$sign" "$hours" "$minutes"
  fi
}

# Fix timezone format from +HH:MM to +HHMM
fix_colon_tz() {
  echo "$1" | sed -E 's/([+-][0-9]{2}):?([0-9]{2})$/\1\2/'
}

# Convert local time with timezone to UTC
to_utc() {
  python3 - "$1" <<'PY'
import sys
from datetime import datetime, timezone
s = sys.argv[1]
dt = datetime.strptime(s, '%Y:%m:%d %H:%M:%S%z')
print(dt.astimezone(timezone.utc).strftime('%Y:%m:%d %H:%M:%S'))
PY
}

# Get timezone for a video file
# Priority: timezone.txt → existing metadata → CLI/country
get_timezone() {
  local file="$1" 
  local cli_tz="${2:-}"
  local dir tz dto
  dir="$(dirname "$file")"

  # 1. Check for local timezone.txt file (explicit override)
  if [[ -f "$dir/timezone.txt" ]]; then
    tz="$(head -n1 "$dir/timezone.txt")"
    chflags hidden "$dir/timezone.txt" 2>/dev/null || true
    echo "$(fix_colon_tz "$tz")"
    TZ_SOURCE="timezone.txt"
    return 0
  fi

  # 2. Check if file already has timezone in DateTimeOriginal (respect existing - don't modify)
  dto="$(exiftool -s3 -DateTimeOriginal "$file" 2>/dev/null || true)"
  if [[ "$dto" =~ [+-][0-9]{2}(:?[0-9]{2})$ ]]; then
    echo "$(fix_colon_tz "${dto:19}")"
    TZ_SOURCE="existing metadata"
    return 0
  fi

  # 3. Apply CLI/country timezone (when no existing timezone set)
  if [[ -n "$cli_tz" ]]; then
    echo "$(fix_colon_tz "$cli_tz")"
    TZ_SOURCE="CLI/country"
    return 0
  fi

  return 1
}

# Get local datetime for a video file
# Priority: filename → DateTimeOriginal → MediaCreateDate → mtime
get_datetime_local() {
  local file="$1" base dto mcd
  base="$(basename "$file")"

  if [[ "$base" =~ ^(VID|LRV|IMG)_([0-9]{8})_([0-9]{6}) ]]; then
    local d="${BASH_REMATCH[2]}" t="${BASH_REMATCH[3]}"
    DT_SOURCE="filename"
    echo "${d:0:4}:${d:4:2}:${d:6:2} ${t:0:2}:${t:2:2}:${t:4:2}"
    return 0
  fi

  dto="$(exiftool -s3 -DateTimeOriginal "$file" 2>/dev/null || true)"
  if [[ "$dto" =~ ^([0-9]{4}):([0-9]{2}):([0-9]{2})[[:space:]]([0-9]{2}):([0-9]{2}):([0-9]{2}) ]]; then
    DT_SOURCE="DateTimeOriginal"
    echo "${BASH_REMATCH[1]}:${BASH_REMATCH[2]}:${BASH_REMATCH[3]} ${BASH_REMATCH[4]}:${BASH_REMATCH[5]}:${BASH_REMATCH[6]}"
    return 0
  fi

  mcd="$(exiftool -s3 -QuickTime:MediaCreateDate "$file" 2>/dev/null || true)"
  if [[ "$mcd" =~ ^([0-9]{4}):([0-9]{2}):([0-9]{2})[[:space:]]([0-9]{2}):([0-9]{2}):([0-9]{2}) ]]; then
    DT_SOURCE="MediaCreateDate"
    echo "${BASH_REMATCH[1]}:${BASH_REMATCH[2]}:${BASH_REMATCH[3]} ${BASH_REMATCH[4]}:${BASH_REMATCH[5]}:${BASH_REMATCH[6]}"
    return 0
  fi

  DT_SOURCE="file mtime"
  date -r "$file" +%Y:%m:%d\ %H:%M:%S
}

# Update video file metadata with correct timestamps
update_metadata() {
  local file="$1" local_time="$2" utc_time="$3"
  # Extract just the datetime without timezone for file system timestamps
  local local_time_no_tz="${local_time:0:19}"
  
  exiftool -overwrite_original \
    "-DateTimeOriginal=$local_time" \
    "-QuickTime:CreateDate=$utc_time" \
    "-QuickTime:ModifyDate=$utc_time" \
    "-FileModifyDate=$local_time_no_tz" "$file" >/dev/null 2>&1
  SetFile -d "$(date -j -f "%Y:%m:%d %H:%M:%S" "$local_time_no_tz" "+%m/%d/%Y %H:%M:%S")" "$file"
}

# Get original metadata for a file
get_original_metadata() {
  local file="$1"
  echo "$(exiftool -s3 -DateTimeOriginal -QuickTime:CreateDate -FileModifyDate "$file" 2>/dev/null | paste -s -d' ')"
}

# Calculate time difference between two timestamps
calculate_time_difference() {
  local timestamp1="$1"
  local timestamp2="$2"
  
  # Convert timestamps to seconds since epoch
  local ts1_seconds=$(date -j -f "%Y:%m:%d %H:%M:%S" "${timestamp1:0:19}" "+%s" 2>/dev/null || echo 0)
  local ts2_seconds=$(date -j -f "%Y:%m:%d %H:%M:%S" "${timestamp2:0:19}" "+%s" 2>/dev/null || echo 0)
  
  # Calculate absolute difference in seconds
  local diff=$((ts2_seconds - ts1_seconds))
  if [[ $diff -lt 0 ]]; then
    diff=$((-diff))
  fi
  
  # Convert to human-readable format
  local hours=$((diff / 3600))
  local minutes=$(((diff % 3600) / 60))
  local seconds=$((diff % 60))
  
  if [[ $hours -gt 0 ]]; then
    printf "%dh %dm %ds" $hours $minutes $seconds
  elif [[ $minutes -gt 0 ]]; then
    printf "%dm %ds" $minutes $seconds
  else
    printf "%ds" $seconds
  fi
}