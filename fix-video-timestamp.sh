#!/bin/bash
# fix-video-timestamp.sh
# Fixes a single video file timestamp using filename patterns or EXIF data
# Requires: exiftool, SetFile, python3
# Usage: ./fix-video-timestamp.sh VIDEO_FILE [--apply] [--country COUNTRY | --timezone +HHMM] [--verbose]

set -euo pipefail
IFS=$'\n\t'

apply=0
verbose=0
cli_tz=""
cli_country=""
TZ_SOURCE=""  # Global variable to track timezone source  
DT_SOURCE=""  # Global variable to track datetime source
video_file=""

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
      echo "Usage: fix-video-timestamp.sh VIDEO_FILE [OPTIONS]"
      echo "Options:"
      echo "  --apply         Apply changes (default: dry run)"
      echo "  --verbose, -v   Show detailed processing info"  
      echo "  --timezone TZ   Use specific timezone (+HHMM format)"
      echo "  --country NAME  Use country name/code for timezone lookup"
      echo "  --help, -h      Show this help"
      exit 0 ;;
    -*) echo "ERROR: Unknown option $1" >&2; exit 1 ;;
    *) 
      [[ -z "$video_file" ]] || { echo "ERROR: Only one video file allowed" >&2; exit 1; }
      video_file="$1"
      shift ;;
  esac
done

# Validate required arguments
[[ -n "$video_file" ]] || { echo "ERROR: VIDEO_FILE is required" >&2; exit 1; }
[[ -f "$video_file" ]] || { echo "ERROR: File not found: $video_file" >&2; exit 1; }

# Convert country to timezone if provided
if [[ -n "$cli_country" && -z "$cli_tz" ]]; then
  if cli_tz=$(get_timezone_for_country "$cli_country"); then
    # If it's a 2-letter code, show both code and full name
    if [[ ${#cli_country} -eq 2 ]]; then
      # Look up the full country name from the CSV
      country_code="$(echo "$cli_country" | tr '[:lower:]' '[:upper:]')"
      # Handle CSV with potential quotes and commas in country names
      country_name="$(grep "^$country_code," "$TIMEZONE_DIR/country.csv" 2>/dev/null | sed "s/^$country_code,//" | sed 's/^"//;s/"$//' || echo "$cli_country")"
      echo "🌍 Country: $country_code ($country_name) → Timezone: $cli_tz"
    else
      echo "🌍 Country: $cli_country → Timezone: $cli_tz"
    fi
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

# A) TIMEZONE picking (timezone.txt → existing metadata → CLI/country)
get_timezone() {
  local file="$1" dir tz dto
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

# B) DATETIME picking (filename → DateTimeOriginal → MediaCreateDate → mtime)
get_datetime_local() {
  local file="$1" base dto mcd
  base="$(basename "$file")"

  if [[ "$base" =~ ^VID_([0-9]{8})_([0-9]{6}) ]]; then
    local d="${BASH_REMATCH[1]}" t="${BASH_REMATCH[2]}"
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

# ---------- logging helpers ----------
log_verbose() {
  [[ $verbose -eq 1 ]] && echo "$@" >&2
}

# ---------- original metadata helpers ----------
get_original_metadata() {
  local file="$1"
  
  # Try to get DateTimeOriginal with timezone
  local dto="$(exiftool -s3 -DateTimeOriginal "$file" 2>/dev/null || true)"
  if [[ -n "$dto" ]]; then
    echo "$dto"
    return 0
  fi
  
  # Try MediaCreateDate
  local mcd="$(exiftool -s3 -QuickTime:MediaCreateDate "$file" 2>/dev/null || true)"
  if [[ -n "$mcd" ]]; then
    echo "$mcd"
    return 0
  fi
  
  # Fallback to file modification time
  local mtime="$(date -r "$file" '+%Y:%m:%d %H:%M:%S' 2>/dev/null || true)"
  if [[ -n "$mtime" ]]; then
    echo "$mtime (file mtime)"
    return 0
  fi
  
  return 1
}

calculate_time_difference() {
  local original="$1"
  local corrected="$2"
  
  # Convert both timestamps to UTC for comparison
  local orig_utc=""
  local corr_utc=""
  
  # Convert original to UTC if it has timezone info
  if [[ "$original" =~ [+-][0-9]{2}:?[0-9]{2}$ ]]; then
    orig_utc="$(to_utc "$original" 2>/dev/null || echo "")"
  else
    # No timezone in original - need to determine what the original represents
    # If the original time matches the filename time, it's likely already in local time
    # Otherwise assume it's UTC
    local orig_time_only="$(echo "$original" | sed -E 's/ \(.*\)$//')"  # Remove (file mtime) suffix
    
    # Extract just the time portion from corrected (local time from filename)
    local corrected_time_only="$(echo "$corrected" | sed -E 's/[+-][0-9]{2}:?[0-9]{2}$//')"
    
    if [[ "$orig_time_only" == "$corrected_time_only" ]]; then
      # Original already shows local time, no change needed
      echo "No change"
      return 0
    else
      # Original is different from filename time, likely UTC
      orig_utc="$orig_time_only"
    fi
    
    # Get corrected UTC 
    corr_utc="$(to_utc "$corrected" 2>/dev/null || echo "")"
    
    if [[ -n "$orig_utc" && -n "$corr_utc" ]]; then
      # Calculate the difference
      local orig_epoch=$(date -j -f "%Y:%m:%d %H:%M:%S" "$orig_utc" "+%s" 2>/dev/null || echo "0")
      local corr_epoch=$(date -j -f "%Y:%m:%d %H:%M:%S" "$corr_utc" "+%s" 2>/dev/null || echo "0")
      
      if [[ "$orig_epoch" -ne 0 && "$corr_epoch" -ne 0 ]]; then
        local diff=$((corr_epoch - orig_epoch))
        local abs_diff=$((diff < 0 ? -diff : diff))
        
        if [[ $abs_diff -eq 0 ]]; then
          echo "No change (same UTC time)"
          return 0
        fi
        
        local hours=$((abs_diff / 3600))
        local minutes=$(((abs_diff % 3600) / 60))
        local sign=$([[ $diff -lt 0 ]] && echo "-" || echo "+")
        
        local change_desc=""
        if [[ $hours -gt 0 && $minutes -gt 0 ]]; then
          change_desc="${sign}${hours}h ${minutes}m"
        elif [[ $hours -gt 0 ]]; then
          change_desc="${sign}${hours}h"
        elif [[ $minutes -gt 0 ]]; then
          change_desc="${sign}${minutes}m"
        else
          change_desc="${sign}<1m"
        fi
        
        # Extract timezone for context and explain the change
        if [[ "$corrected" =~ ([+-][0-9]{2}:?[0-9]{2})$ ]]; then
          local tz_display="${BASH_REMATCH[1]}"
          echo "$change_desc"
        else
          echo "$change_desc (setting timezone)"
        fi
        return 0
      fi
    fi
    
    # Fallback if calculation fails
    echo "Setting timezone"
    return 0
  fi
  
  # Convert corrected to UTC
  corr_utc="$(to_utc "$corrected" 2>/dev/null || echo "")"
  
  if [[ -z "$orig_utc" || -z "$corr_utc" ]]; then
    echo "Unable to calculate"
    return 1
  fi
  
  # Parse UTC timestamps for epoch conversion
  local orig_clean="$(echo "$orig_utc" | sed -E 's/([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}).*/\1/')"
  local corr_clean="$(echo "$corr_utc" | sed -E 's/([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}).*/\1/')"
  
  # Convert to epoch seconds
  local orig_epoch=$(date -j -f "%Y:%m:%d %H:%M:%S" "$orig_clean" "+%s" 2>/dev/null || echo "0")
  local corr_epoch=$(date -j -f "%Y:%m:%d %H:%M:%S" "$corr_clean" "+%s" 2>/dev/null || echo "0")
  
  if [[ "$orig_epoch" -eq 0 || "$corr_epoch" -eq 0 ]]; then
    echo "Unable to calculate"
    return 1
  fi
  
  local diff=$((corr_epoch - orig_epoch))
  local abs_diff=$((diff < 0 ? -diff : diff))
  
  if [[ $abs_diff -eq 0 ]]; then
    echo "No change"
    return 0
  fi
  
  local hours=$((abs_diff / 3600))
  local minutes=$(((abs_diff % 3600) / 60))
  local sign=$([[ $diff -lt 0 ]] && echo "-" || echo "+")
  
  if [[ $hours -gt 0 && $minutes -gt 0 ]]; then
    echo "${sign}${hours}h ${minutes}m"
  elif [[ $hours -gt 0 ]]; then
    echo "${sign}${hours}h"
  elif [[ $minutes -gt 0 ]]; then
    echo "${sign}${minutes}m"
  else
    echo "${sign}<1m"
  fi
}

# ---------- main processing ----------
process_video_file() {
  local file="$1"
  local base="$(basename "$file")"
  
  log_verbose "Processing: $file"
  
  # Check if metadata already has timezone - if so, use metadata time too
  local dto_with_tz="$(exiftool -s3 -DateTimeOriginal "$file" 2>/dev/null || true)"
  if [[ "$dto_with_tz" =~ ^([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2})([+-][0-9]{2}:?[0-9]{2})$ ]]; then
    # Metadata already has complete time+timezone, use it as-is
    local_dt="${BASH_REMATCH[1]}"
    tz="$(fix_colon_tz "${BASH_REMATCH[2]}")"
    TZ_SOURCE="existing metadata"
    DT_SOURCE="existing metadata" 
    log_verbose "  Using existing metadata: $local_dt with timezone $tz"
  else
    # No existing timezone in metadata, proceed with normal logic
    
    # Get timezone for this file
    local tz_result
    if ! tz_result="$(get_timezone "$file")"; then
      echo "❌ $base: No timezone (use --timezone or timezone.txt). Aborting." >&2
      return 1
    fi
    tz="$tz_result"
    # Set TZ_SOURCE based on timezone logic
    if [[ -f "$(dirname "$file")/timezone.txt" ]]; then
      TZ_SOURCE="timezone.txt"
    elif exiftool -s3 -DateTimeOriginal "$file" 2>/dev/null | grep -q '[+-][0-9][0-9]'; then
      TZ_SOURCE="existing metadata"
    else
      TZ_SOURCE="CLI/country"
    fi
    log_verbose "  Timezone: $tz (source: $TZ_SOURCE)"

    # Get local datetime - prioritize filename for VID files
    local_dt="$(get_datetime_local "$file")"
    # Set DT_SOURCE based on file type
    base="$(basename "$file")"
    if [[ "$base" =~ ^VID_([0-9]{8})_([0-9]{6}) ]]; then
      DT_SOURCE="filename"
    elif exiftool -s3 -DateTimeOriginal "$file" 2>/dev/null | grep -q '^[0-9][0-9][0-9][0-9]:[0-9][0-9]:[0-9][0-9]'; then
      DT_SOURCE="DateTimeOriginal"
    elif exiftool -s3 -QuickTime:MediaCreateDate "$file" 2>/dev/null | grep -q '^[0-9][0-9][0-9][0-9]:[0-9][0-9]:[0-9][0-9]'; then
      DT_SOURCE="MediaCreateDate"
    else
      DT_SOURCE="file mtime"
    fi
    log_verbose "  Local datetime: $local_dt (source: $DT_SOURCE)"
  fi
  
  local_with_tz="${local_dt}${tz}"
  log_verbose "  Local with TZ: $local_with_tz"
  
  # Convert to UTC
  utc_time="$(to_utc "$local_with_tz")"
  log_verbose "  UTC time: $utc_time"

  # Get original metadata for comparison
  if original_meta="$(get_original_metadata "$file")"; then
    log_verbose "  Original metadata: $original_meta"
    time_diff="$(calculate_time_difference "$original_meta" "$local_with_tz")"
    log_verbose "  Time difference: $time_diff"
  else
    original_meta="No original metadata"
    time_diff="N/A"
  fi

  # Display enhanced comparison info
  printf "\033[36m🔍 %s\033[0m\n" "$base"
  printf "📅 Original : %s (from %s, tz: %s)\n" "$original_meta" "$DT_SOURCE" "$TZ_SOURCE"
  printf "⏱️ Corrected: %s\n" "$local_with_tz"
  printf "🌐 UTC      : %s UTC\n" "$utc_time"
  printf "📊 Change   : %s\n" "$time_diff"

  # Update metadata if in apply mode
  if [[ $apply -eq 1 ]]; then
    log_verbose "  Updating metadata..."
    update_metadata "$file" "$local_with_tz" "$utc_time"
    log_verbose "  ✅ Metadata updated"
    echo "✅ Applied changes to $base"
  else
    log_verbose "  [DRY RUN] Would update metadata"
    echo "🧪 DRY RUN - use --apply to update metadata"
  fi
  
  echo  # Empty line for readability
  return 0
}

# ---------- main ----------
echo "🕓 Processing video file: $(basename "$video_file")"
echo

if process_video_file "$video_file"; then
  if [[ $apply -eq 1 ]]; then
    echo "✅ Video timestamp processing complete - changes applied."
  else  
    echo "✅ Video timestamp processing complete - DRY RUN (no changes made)."
  fi
else
  echo "❌ Video timestamp processing failed."
  exit 1
fi