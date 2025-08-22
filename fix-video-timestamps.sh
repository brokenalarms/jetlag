#!/bin/bash
# fix-video-timestamps.sh
# Fixes video file timestamps using filename patterns or EXIF data
# Requires: exiftool, SetFile, python3
# Usage: ./fix-video-timestamps.sh [--apply] [--country COUNTRY | --timezone +HHMM] [--verbose]
# Scans current directory for *.mp4/*.mov files and normalizes their timestamps

set -euo pipefail
IFS=$'\n\t'

apply=0
verbose=0
cli_tz=""
cli_country=""

# Get script directory for timezone CSV files
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMEZONE_DIR="$SCRIPT_DIR/timezones"

# CSV-based timezone lookup
get_timezone_for_country() {
  local input="$1"
  local country_code=""
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

# ---------- args ----------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) apply=1; shift ;;
    --verbose|-v) verbose=1; shift ;;
    --timezone)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --timezone needs +HHMM or +HH:MM"; exit 1; }
      cli_tz="$1"; shift ;;
    --country)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --country requires a country name/code"; exit 1; }
      cli_country="$1"; shift ;;
    --help|-h) 
      echo "Usage: normalize_insta360_timestamps.sh [OPTIONS]"
      echo "Options:"
      echo "  --apply         Apply changes (default: dry run)"
      echo "  --verbose, -v   Show detailed processing info"  
      echo "  --timezone TZ   Use specific timezone (+HHMM format)"
      echo "  --country NAME  Use country name/code for timezone lookup"
      echo "  --help, -h      Show this help"
      exit 0 ;;
    *) shift ;;
  esac
done

# Convert country to timezone if provided
if [[ -n "$cli_country" && -z "$cli_tz" ]]; then
  if cli_tz=$(get_timezone_for_country "$cli_country"); then
    echo "🌍 Country: $cli_country → Timezone: $cli_tz"
  else
    echo "ERROR: Unknown country '$cli_country'." >&2
    echo "Supported formats:" >&2
    echo "  - 2-letter country codes (e.g., US, GB, FR, DE, JP)" >&2
    echo "  - Full country names (e.g., 'United States', 'United Kingdom', 'France')" >&2
    exit 1
  fi
fi

# ---------- helpers ----------
fix_colon_tz() {
  echo "$1" | sed -E 's/([+-][0-9]{2}):?([0-9]{2})$/\1\2/'
}

to_utc() {
  python3 - "$1" <<'PY'
import sys
from datetime import datetime, timezone
s = sys.argv[1]
dt = datetime.strptime(s, '%Y:%m:%d %H:%M:%S%z')
print(dt.astimezone(timezone.utc).strftime('%Y:%m:%d %H:%M:%S'))
PY
}

# A) TIMEZONE picking (CLI → timezone.txt → DateTimeOriginal)
get_timezone() {
  local file="$1" dir tz dto
  dir="$(dirname "$file")"

  if [[ -n "$cli_tz" ]]; then
    echo "$(fix_colon_tz "$cli_tz")"
    return 0
  fi

  if [[ -f "$dir/timezone.txt" ]]; then
    tz="$(head -n1 "$dir/timezone.txt")"
    chflags hidden "$dir/timezone.txt" 2>/dev/null || true
    echo "$(fix_colon_tz "$tz")"
    return 0
  fi

  dto="$(exiftool -s3 -DateTimeOriginal "$file" 2>/dev/null || true)"
  if [[ "$dto" =~ [+-][0-9]{2}(:?[0-9]{2})$ ]]; then
    echo "$(fix_colon_tz "${dto:19}")"
    return 0
  fi

  return 1
}

# B) DATETIME picking (filename → DateTimeOriginal → MediaCreateDate → mtime)
get_datetime_local() {
  local file="$1" base dto mcd
  base="$(basename "$file")"

  if [[ "$base" =~ ^VID_([0-9]{8})_([0-9]{6}) ]]; then
    local d="${BASH_REMATCH[1]}" t="${BASH_REMATCH[2]}"
    echo "${d:0:4}:${d:4:2}:${d:6:2} ${t:0:2}:${t:2:2}:${t:4:2}"
    return 0
  fi

  dto="$(exiftool -s3 -DateTimeOriginal "$file" 2>/dev/null || true)"
  if [[ "$dto" =~ ^([0-9]{4}):([0-9]{2}):([0-9]{2})[[:space:]]([0-9]{2}):([0-9]{2}):([0-9]{2}) ]]; then
    echo "${BASH_REMATCH[1]}:${BASH_REMATCH[2]}:${BASH_REMATCH[3]} ${BASH_REMATCH[4]}:${BASH_REMATCH[5]}:${BASH_REMATCH[6]}"
    return 0
  fi

  mcd="$(exiftool -s3 -QuickTime:MediaCreateDate "$file" 2>/dev/null || true)"
  if [[ "$mcd" =~ ^([0-9]{4}):([0-9]{2}):([0-9]{2})[[:space:]]([0-9]{2}):([0-9]{2}):([0-9]{2}) ]]; then
    echo "${BASH_REMATCH[1]}:${BASH_REMATCH[2]}:${BASH_REMATCH[3]} ${BASH_REMATCH[4]}:${BASH_REMATCH[5]}:${BASH_REMATCH[6]}"
    return 0
  fi

  date -r "$file" +%Y:%m:%d\ %H:%M:%S
}

update_metadata() {
  local file="$1" local_time="$2" utc_time="$3"
  exiftool -overwrite_original \
    "-DateTimeOriginal=$local_time" \
    "-QuickTime:CreateDate=$utc_time" \
    "-QuickTime:ModifyDate=$utc_time" \
    "-FileModifyDate=$utc_time" "$file" >/dev/null 2>&1
  SetFile -d "$(date -j -f "%Y:%m:%d %H:%M:%S" "${local_time:0:19}" "+%m/%d/%Y %H:%M:%S")" "$file"
}

# ---------- logging helpers ----------
log_verbose() {
  [[ $verbose -eq 1 ]] && echo "$@" >&2
}

# ---------- single file processing ----------
process_single_file() {
  local file="$1"
  local base="$(basename "$file")"
  
  log_verbose "Processing: $file"
  
  # Get timezone for this file
  if ! tz="$(get_timezone "$file")"; then
    echo "❌ $base: No timezone (use --timezone or timezone.txt). Aborting." >&2
    return 1
  fi
  log_verbose "  Timezone: $tz"

  # Get local datetime
  local_dt="$(get_datetime_local "$file")"
  log_verbose "  Local datetime: $local_dt"
  
  local_with_tz="${local_dt}${tz}"
  log_verbose "  Local with TZ: $local_with_tz"
  
  # Convert to UTC
  utc_time="$(to_utc "$local_with_tz")"
  log_verbose "  UTC time: $utc_time"

  # Display file processing info
  printf "\033[36m🔍 %s\033[0m\n" "$base"
  printf "⏱️ Local : %s\n" "$local_with_tz"
  printf "🌐 UTC   : %s UTC\n" "$utc_time"

  # Update metadata if in apply mode
  if [[ $apply -eq 1 ]]; then
    log_verbose "  Updating metadata..."
    update_metadata "$file" "$local_with_tz" "$utc_time"
    log_verbose "  ✅ Metadata updated"
  else
    log_verbose "  [DRY RUN] Would update metadata"
  fi
  
  echo  # Empty line for readability
  return 0
}

# ---------- main ----------
echo "🕓 Scanning video files..."

find . -type f \( -iname '*.mp4' -o -iname '*.mov' \) -print0 | while IFS= read -r -d '' file; do
  process_single_file "$file" || exit 1
done

echo "✅ Timestamp normalization complete."
