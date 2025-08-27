#!/bin/bash
# Library - Timestamp fixing functions for video files
# Not executable directly - source this file from other scripts

# ============================================================================
# Generic timestamp reading/writing functions
# ============================================================================

# Global variables for timestamp data
FILE_BIRTHTIME=""
FILE_MTIME=""
DATETIME_ORIGINAL=""
MEDIA_CREATE_DATE=""
FILENAME_DATE=""
TIMESTAMP_SOURCE=""

# Get all timestamps from a file
# Returns associative array with: file_birthtime, file_mtime, datetime_original, media_create_date, filename_date
# Usage: get_file_timestamps "/path/to/file.mp4"
# Sets global variables: FILE_BIRTHTIME, FILE_MTIME, DATETIME_ORIGINAL, MEDIA_CREATE_DATE, FILENAME_DATE
get_file_timestamps() {
  local file="$1"
  local base="$(basename "$file")"
  
  # Reset global variables
  FILE_BIRTHTIME=""
  FILE_MTIME=""
  DATETIME_ORIGINAL=""
  MEDIA_CREATE_DATE=""
  FILENAME_DATE=""
  
  # Get file system timestamps
  FILE_BIRTHTIME="$(stat -f "%SB" -t "%Y:%m:%d %H:%M:%S" "$file" 2>/dev/null || true)"
  FILE_MTIME="$(date -r "$file" '+%Y:%m:%d %H:%M:%S' 2>/dev/null || true)"
  
  # Parse filename for date patterns (comprehensive set from lib-file-ops.sh)
  if [[ "$base" =~ ^(VID|LRV|IMG)_([0-9]{8})_([0-9]{6}) ]]; then
    # VID_YYYYMMDD_HHMMSS, IMG_YYYYMMDD_HHMMSS, LRV_YYYYMMDD_HHMMSS (Insta360)
    local d="${BASH_REMATCH[2]}" t="${BASH_REMATCH[3]}"
    FILENAME_DATE="${d:0:4}:${d:4:2}:${d:6:2} ${t:0:2}:${t:2:2}:${t:4:2}"
  elif [[ "$base" =~ DJI_([0-9]{4})([0-9]{2})([0-9]{2})([0-9]{6})_ ]]; then
    # DJI_YYYYMMDDHHMMSS_* (DJI Mavic 3 and newer)
    local d="${BASH_REMATCH[1]}${BASH_REMATCH[2]}${BASH_REMATCH[3]}" t="${BASH_REMATCH[4]}"
    FILENAME_DATE="${d:0:4}:${d:4:2}:${d:6:2} ${t:0:2}:${t:2:2}:${t:4:2}"
  elif [[ "$base" =~ DSC_([0-9]{4})([0-9]{2})([0-9]{2})_ ]]; then
    # DSC_YYYYMMDD_HHMMSS (Sony cameras)
    local d="${BASH_REMATCH[1]}${BASH_REMATCH[2]}${BASH_REMATCH[3]}"
    FILENAME_DATE="${d:0:4}:${d:4:2}:${d:6:2} 00:00:00"  # No time in pattern, use 00:00:00
  elif [[ "$base" =~ Screenshot[[:space:]]([0-9]{4})-([0-9]{2})-([0-9]{2})[[:space:]]at[[:space:]]([0-9]{1,2})\.([0-9]{2})\.([0-9]{2}) ]]; then
    # Screenshot YYYY-MM-DD at HH.MM.SS (macOS screenshots)
    FILENAME_DATE="${BASH_REMATCH[1]}:${BASH_REMATCH[2]}:${BASH_REMATCH[3]} ${BASH_REMATCH[4]}:${BASH_REMATCH[5]}:${BASH_REMATCH[6]}"
  elif [[ "$base" =~ ([0-9]{4})([0-9]{2})([0-9]{2}) ]]; then
    # Generic YYYYMMDD anywhere in filename
    local year="${BASH_REMATCH[1]}" month="${BASH_REMATCH[2]}" day="${BASH_REMATCH[3]}"
    # Validation: year 2000-2099, month 01-12, day 01-31
    if [[ 10#$year -ge 2000 && 10#$year -le 2099 && 10#$month -ge 1 && 10#$month -le 12 && 10#$day -ge 1 && 10#$day -le 31 ]]; then
      FILENAME_DATE="${year}:${month}:${day} 00:00:00"
    fi
  fi
  
  # Get metadata timestamps with a single exiftool call
  # Use -s (not -s3) to get field names so we can identify which is which
  local metadata_output
  metadata_output=$(exiftool -s -DateTimeOriginal -QuickTime:MediaCreateDate "$file" 2>/dev/null || true)
  
  # Parse the metadata output
  if [[ "$metadata_output" =~ DateTimeOriginal[[:space:]]*:[[:space:]]*([-0-9: +:]+) ]]; then
    DATETIME_ORIGINAL="${BASH_REMATCH[1]}"
  fi
  if [[ "$metadata_output" =~ MediaCreateDate[[:space:]]*:[[:space:]]*([-0-9: +:]+) ]]; then
    MEDIA_CREATE_DATE="${BASH_REMATCH[1]}"
  fi
  
  return 0
}

# Get the best timestamp to use based on priority
# Priority: 1. Filename (for VID/IMG/LRV), 2. DateTimeOriginal, 3. MediaCreateDate, 4. File birthtime
# Returns: timestamp and sets global TIMESTAMP_SOURCE
get_best_timestamp() {
  local file="$1"
  
  # Get all timestamps
  get_file_timestamps "$file"
  
  local base="$(basename "$file")"
  local timestamp=""
  TIMESTAMP_SOURCE=""
  
  # For VID/IMG/LRV files with parseable names, ALWAYS prioritize filename
  if [[ -n "$FILENAME_DATE" ]] && [[ "$base" =~ ^(VID|LRV|IMG)_[0-9]{8}_[0-9]{6} ]]; then
    timestamp="$FILENAME_DATE"
    TIMESTAMP_SOURCE="filename"
  elif [[ -n "$DATETIME_ORIGINAL" ]] && [[ "$DATETIME_ORIGINAL" =~ [0-9] ]]; then
    # Extract just the datetime part (remove timezone if present)
    timestamp="$(echo "$DATETIME_ORIGINAL" | sed -E 's/([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}).*/\1/')"
    TIMESTAMP_SOURCE="DateTimeOriginal"
  elif [[ -n "$MEDIA_CREATE_DATE" ]] && [[ "$MEDIA_CREATE_DATE" =~ [0-9] ]]; then
    timestamp="$(echo "$MEDIA_CREATE_DATE" | sed -E 's/([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}).*/\1/')"
    TIMESTAMP_SOURCE="MediaCreateDate"
  elif [[ -n "$FILE_BIRTHTIME" ]]; then
    timestamp="$FILE_BIRTHTIME"
    TIMESTAMP_SOURCE="file birthtime"
  elif [[ -n "$FILE_MTIME" ]]; then
    timestamp="$FILE_MTIME"
    TIMESTAMP_SOURCE="file mtime"
  fi
  
  echo "$timestamp"
  return 0
}

# Set all timestamps for a file (metadata and file system)
# Usage: set_file_timestamps "/path/to/file.mp4" "2024:01:01 12:00:00+0100" "2024:01:01 11:00:00"
set_file_timestamps() {
  local file="$1"
  local local_with_tz="$2"  # Local time with timezone (e.g., "2024:01:01 12:00:00+0100")
  local utc_time="$3"        # UTC time (e.g., "2024:01:01 11:00:00")
  
  # Extract just the datetime without timezone for file system timestamps
  local local_time_no_tz="${local_with_tz:0:19}"
  
  # Update metadata with a single exiftool call
  exiftool -overwrite_original \
    "-DateTimeOriginal=$local_with_tz" \
    "-QuickTime:CreateDate=$utc_time" \
    "-QuickTime:ModifyDate=$utc_time" \
    "-FileModifyDate=$local_time_no_tz" "$file" >/dev/null 2>&1
  
  # Update macOS file creation date
  SetFile -d "$(date -j -f "%Y:%m:%d %H:%M:%S" "$local_time_no_tz" "+%m/%d/%Y %H:%M:%S")" "$file" 2>/dev/null || true
  
  return 0
}

# Get date in YYYY-MM-DD format for file organization
# Uses same priority as get_best_timestamp but returns date only
get_file_date_for_organization() {
  local file="$1"
  
  # Use get_best_timestamp to get the best timestamp, then extract date
  local timestamp
  if ! timestamp="$(get_best_timestamp "$file")"; then
    return 1
  fi
  
  # Extract date portion (YYYY:MM:DD) and convert to YYYY-MM-DD
  local date_str="${timestamp:0:4}-${timestamp:5:2}-${timestamp:8:2}"
  
  echo "$date_str"
  return 0
}

# Expand path template with file and location context
# Usage: expand_path_template TEMPLATE FILE_DATE [LOCATION]
# Template variables: {{year}}, {{date}}, {{location}}
expand_path_template() {
  local template="$1"
  local file_date="$2"  # YYYY-MM-DD format
  local location="${3:-}"
  
  # Extract year from date (YYYY-MM-DD -> YYYY)
  local year="${file_date:0:4}"
  
  # Replace template variables
  local expanded="$template"
  expanded="${expanded//\{\{year\}\}/$year}"
  expanded="${expanded//\{\{date\}\}/$file_date}"
  expanded="${expanded//\{\{location\}\}/$location}"
  
  # Clean up any remaining empty location placeholders
  expanded="${expanded//\/\//_}"
  expanded="${expanded%/}"
  
  echo "$expanded"
}

# Get timestamp comparison data for analysis
# Returns structured data about file vs metadata timestamps
get_timestamp_comparison() {
  local file="$1"
  
  # Get all timestamps
  get_file_timestamps "$file"
  
  local file_timestamp="$FILE_BIRTHTIME"
  local metadata_timestamp=""
  local metadata_source=""
  local differs="false"
  
  # Determine which metadata has value
  if [[ -n "$DATETIME_ORIGINAL" ]] && [[ "$DATETIME_ORIGINAL" =~ [0-9] ]]; then
    metadata_timestamp="$(echo "$DATETIME_ORIGINAL" | sed -E 's/([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}).*/\1/')"
    metadata_source="DateTimeOriginal"
  elif [[ -n "$MEDIA_CREATE_DATE" ]] && [[ "$MEDIA_CREATE_DATE" =~ [0-9] ]]; then
    metadata_timestamp="$(echo "$MEDIA_CREATE_DATE" | sed -E 's/([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}).*/\1/')"
    metadata_source="MediaCreateDate"
  fi
  
  # Check if file date and metadata differ significantly
  if [[ -n "$file_timestamp" && -n "$metadata_timestamp" ]]; then
    local file_date_only="${file_timestamp:0:10}"
    local meta_date_only="${metadata_timestamp:0:10}"
    
    # Check if file date is 1980 (common reset date) or differs from metadata
    if [[ "$file_date_only" == "1980:01:01" ]] || [[ "$file_date_only" != "$meta_date_only" ]]; then
      differs="true"
    fi
  fi
  
  # Use file mtime as fallback if no birthtime
  if [[ -z "$file_timestamp" && -n "$FILE_MTIME" ]]; then
    file_timestamp="$FILE_MTIME"
  fi
  
  # Output structured data (pipe-separated for easy parsing)
  echo "${file_timestamp}|${metadata_timestamp}|${metadata_source}|${differs}"
}

# Calculate time difference between two timestamps in seconds
# Returns: difference_in_seconds|status
# Status: "no_change", "setting_timezone", "unable_to_calculate", or "calculated"
calculate_timestamp_delta_seconds() {
  local original="$1"
  local corrected="$2"
  
  # Convert both timestamps to UTC for comparison
  local orig_utc=""
  local corr_utc=""
  
  # Convert original to UTC if it has timezone info
  if [[ "$original" =~ [+-][0-9]{2}:?[0-9]{2}$ ]]; then
    orig_utc="$(to_utc "$original" 2>/dev/null || echo "")"
  else
    # No timezone in original - extract just the datetime part
    local orig_time_only="$(echo "$original" | sed -E 's/ \(.*\)$//')"
    
    # Extract just the time portion from corrected (local time from filename)
    local corrected_time_only="$(echo "$corrected" | sed -E 's/[+-][0-9]{2}:?[0-9]{2}$//')"
    
    if [[ "$orig_time_only" == "$corrected_time_only" ]]; then
      # Original already shows local time, no change needed
      echo "0|no_change"
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
        echo "$diff|calculated"
        return 0
      fi
    fi
    
    # Fallback if calculation fails
    echo "0|setting_timezone"
    return 0
  fi
  
  # Convert corrected to UTC
  corr_utc="$(to_utc "$corrected" 2>/dev/null || echo "")"
  
  if [[ -z "$orig_utc" || -z "$corr_utc" ]]; then
    echo "0|unable_to_calculate"
    return 1
  fi
  
  # Parse UTC timestamps for epoch conversion
  local orig_clean="$(echo "$orig_utc" | sed -E 's/([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}).*/\1/')"
  local corr_clean="$(echo "$corr_utc" | sed -E 's/([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}).*/\1/')"
  
  # Convert to epoch seconds
  local orig_epoch=$(date -j -f "%Y:%m:%d %H:%M:%S" "$orig_clean" "+%s" 2>/dev/null || echo "0")
  local corr_epoch=$(date -j -f "%Y:%m:%d %H:%M:%S" "$corr_clean" "+%s" 2>/dev/null || echo "0")
  
  if [[ "$orig_epoch" -eq 0 || "$corr_epoch" -eq 0 ]]; then
    echo "0|unable_to_calculate"
    return 1
  fi
  
  local diff=$((corr_epoch - orig_epoch))
  echo "$diff|calculated"
}

# Determine what changes are needed
# Returns description of the change needed
determine_change_needed() {
  local original="$1"       # Original timestamp display (may include "file vs metadata")
  local corrected="$2"      # Corrected timestamp with timezone
  
  # Handle special case where original shows file vs metadata difference
  if [[ "$original" =~ \(file\).*vs.*\((DateTimeOriginal|MediaCreateDate)\) ]]; then
    # Extract the file date and metadata date
    local file_date="$(echo "$original" | sed -E 's/ \(file\).*$//')"
    local meta_date="$(echo "$original" | sed -E 's/.*vs //' | sed -E 's/ \(.*$//')"
    
    # Extract corrected date without timezone
    local corrected_date="${corrected:0:19}"
    
    # Determine what's being fixed and calculate delta
    if [[ "$meta_date" == "$corrected_date" ]]; then
      # Metadata is already correct, just fixing file timestamps
      format_delta_result "$(calculate_timestamp_delta_seconds "$file_date" "$corrected")"
    else
      # Both metadata and file timestamps need fixing (filename differs from metadata)
      format_delta_result "$(calculate_timestamp_delta_seconds "$meta_date" "$corrected")"
    fi
  else
    # Standard comparison - calculate delta from file creation date
    local orig_clean="$(echo "$original" | sed -E 's/ \(.*\)$//')"
    format_delta_result "$(calculate_timestamp_delta_seconds "$orig_clean" "$corrected")"
  fi
}

# Format delta calculation result into human-readable form
format_delta_result() {
  local delta_data="$1"
  IFS='|' read -r delta_sec status <<< "$delta_data"
  
  case "$status" in
    "no_change") echo "No change" ;;
    "setting_timezone") echo "Setting timezone" ;;
    "unable_to_calculate") echo "Unable to calculate" ;;
    "calculated")
      local abs_diff=$((delta_sec < 0 ? -delta_sec : delta_sec))
      
      if [[ $abs_diff -eq 0 ]]; then
        echo "No change"
      else
        local hours=$((abs_diff / 3600))
        local minutes=$(((abs_diff % 3600) / 60))
        local sign=$([[ $delta_sec -lt 0 ]] && echo "-" || echo "+")
        
        if [[ $hours -gt 0 && $minutes -gt 0 ]]; then
          echo "${sign}${hours}h ${minutes}m"
        elif [[ $hours -gt 0 ]]; then
          echo "${sign}${hours}h"
        elif [[ $minutes -gt 0 ]]; then
          echo "${sign}${minutes}m"
        else
          echo "${sign}<1m"
        fi
      fi
      ;;
    *) echo "Unable to calculate" ;;
  esac
}

# ============================================================================
# Timezone and utility functions
# ============================================================================

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

# Get display string for location (includes country name if it's a code)
get_location_display() {
  local input="$1"
  local SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local TIMEZONE_DIR="$SCRIPT_DIR/timezones"
  local country_csv="$TIMEZONE_DIR/country.csv"
  
  # If it's a 2-letter code, show both code and full name
  if [[ ${#input} -eq 2 ]]; then
    local country_code="$(echo "$input" | tr '[:lower:]' '[:upper:]')"
    local country_name="$(grep "^$country_code," "$country_csv" 2>/dev/null | sed "s/^$country_code,//" | sed 's/^"//;s/"$//' || echo "$input")"
    echo "$country_code ($country_name)"
  else
    echo "$input"
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

