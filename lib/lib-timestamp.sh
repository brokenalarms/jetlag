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
KEYS_CREATION_DATE=""
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
  KEYS_CREATION_DATE=""
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
  metadata_output=$(exiftool -s -DateTimeOriginal -QuickTime:MediaCreateDate -Keys:CreationDate "$file" 2>/dev/null || true)
  
  # Parse the metadata output
  if [[ "$metadata_output" =~ DateTimeOriginal[[:space:]]*:[[:space:]]*([-0-9: +:]+) ]]; then
    DATETIME_ORIGINAL="${BASH_REMATCH[1]}"
  fi
  if [[ "$metadata_output" =~ MediaCreateDate[[:space:]]*:[[:space:]]*([-0-9: +:]+) ]]; then
    MEDIA_CREATE_DATE="${BASH_REMATCH[1]}"
  fi
  if [[ "$metadata_output" =~ CreationDate[[:space:]]*:[[:space:]]*([-0-9: +:]+) ]]; then
    KEYS_CREATION_DATE="${BASH_REMATCH[1]}"
  fi
  
  return 0
}

# Get the best timestamp to use based on priority
# Priority: 1. Keys:CreationDate (with tz), 2. DateTimeOriginal (with tz), 3. Filename (VID/IMG/LRV), 
#           4. DateTimeOriginal, 5. MediaCreateDate, 6. File timestamps
# Returns: timestamp and sets global TIMESTAMP_SOURCE
get_best_timestamp() {
  local file="$1"
  
  # Get all timestamps
  get_file_timestamps "$file"
  
  local base="$(basename "$file")"
  local timestamp=""
  TIMESTAMP_SOURCE=""
  
  # Priority 1: Keys:CreationDate with timezone (iPhone videos from Google Photos)
  if [[ -n "$KEYS_CREATION_DATE" ]] && [[ "$KEYS_CREATION_DATE" =~ [+-][0-9]{2}:?[0-9]{2}$ ]]; then
    # Has timezone, extract just the datetime part
    timestamp="$(echo "$KEYS_CREATION_DATE" | sed -E 's/([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}).*/\1/')"
    TIMESTAMP_SOURCE="Keys:CreationDate"
  # Priority 2: DateTimeOriginal with timezone (Insta360 and other cameras)
  elif [[ -n "$DATETIME_ORIGINAL" ]] && [[ "$DATETIME_ORIGINAL" =~ [+-][0-9]{2}:?[0-9]{2}$ ]]; then
    # Has timezone, extract just the datetime part
    timestamp="$(echo "$DATETIME_ORIGINAL" | sed -E 's/([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}).*/\1/')"
    TIMESTAMP_SOURCE="DateTimeOriginal with timezone"
  # Priority 3: Filename for VID/IMG/LRV files with parseable names
  elif [[ -n "$FILENAME_DATE" ]] && [[ "$base" =~ ^(VID|LRV|IMG)_[0-9]{8}_[0-9]{6} ]]; then
    timestamp="$FILENAME_DATE"
    TIMESTAMP_SOURCE="filename"
  # Priority 4: DateTimeOriginal without timezone
  elif [[ -n "$DATETIME_ORIGINAL" ]] && [[ "$DATETIME_ORIGINAL" =~ [0-9] ]]; then
    timestamp="$(echo "$DATETIME_ORIGINAL" | sed -E 's/([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}).*/\1/')"
    TIMESTAMP_SOURCE="DateTimeOriginal"
  # Priority 5: MediaCreateDate (usually UTC)
  elif [[ -n "$MEDIA_CREATE_DATE" ]] && [[ "$MEDIA_CREATE_DATE" =~ [0-9] ]]; then
    timestamp="$(echo "$MEDIA_CREATE_DATE" | sed -E 's/([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}).*/\1/')"
    TIMESTAMP_SOURCE="MediaCreateDate"
  # Priority 6: File timestamps
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
# Usage: expand_path_template TEMPLATE FILE_DATE [LABEL]
# Template variables: {{YYYY}}, {{MM}}, {{MMM}}, {{DD}}, {{YYYY-MM-DD}}, {{label}}
expand_path_template() {
  local template="$1"
  local file_date="$2"  # YYYY-MM-DD format
  local label="${3:-}"
  
  # Check if template contains {{label}} but no label provided
  if [[ "$template" =~ \{\{label\}\} && -z "$label" ]]; then
    echo "ERROR: Template contains {{label}} but no label provided" >&2
    return 1
  fi
  
  # Extract date components (YYYY-MM-DD)
  local year="${file_date:0:4}"
  local month="${file_date:5:2}"
  local day="${file_date:8:2}"
  
  # Month abbreviations array (1-based indexing)
  local months=("" "Jan" "Feb" "Mar" "Apr" "May" "Jun" "Jul" "Aug" "Sep" "Oct" "Nov" "Dec")
  local month_abbr="${months[${month#0}]}"  # Remove leading zero for array index
  
  # Replace template variables
  local expanded="$template"
  expanded="${expanded//\{\{YYYY\}\}/$year}"
  expanded="${expanded//\{\{MM\}\}/$month}"
  expanded="${expanded//\{\{MMM\}\}/$month_abbr}"
  expanded="${expanded//\{\{DD\}\}/$day}"
  expanded="${expanded//\{\{YYYY-MM-DD\}\}/$file_date}"
  expanded="${expanded//\{\{label\}\}/$label}"
  
  # Clean up any remaining empty label placeholders
  expanded="${expanded//\/\//_}"
  expanded="${expanded%/}"
  
  echo "$expanded"
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

# Determine what changes are needed using raw timestamp data
# Usage: determine_change_needed file_timestamp corrected_timestamp_with_tz
determine_change_needed() {
  local file_timestamp="$1"     # Raw file timestamp (from FILE_BIRTHTIME or FILE_MTIME)
  local corrected="$2"          # Corrected timestamp with timezone
  
  # Extract corrected date without timezone for comparison
  local corrected_date="${corrected:0:19}"
  
  # Check if file timestamp needs updating
  local file_needs_update=false
  if [[ -n "$file_timestamp" && "$file_timestamp" != "$corrected_date" ]]; then
    file_needs_update=true
  fi
  
  # For now, focus on file timestamps. Metadata is usually correct when it's the source
  if [[ "$file_needs_update" == true ]]; then
    local result="$(calculate_timestamp_delta_seconds "$file_timestamp" "$corrected")"
    IFS='|' read -r delta_sec status <<< "$result"
    if [[ "$status" == "calculated" ]]; then
      echo "$(format_delta_result "$result" | sed 's/^/File timestamps: /')"
    else
      format_delta_result "$result"
    fi
  else
    echo "No change"
  fi
}

# Format timestamp comparison for display
# Uses global variables set by get_file_timestamps
format_original_timestamps() {
  local file_timestamp="$FILE_BIRTHTIME"
  [[ -z "$file_timestamp" && -n "$FILE_MTIME" ]] && file_timestamp="$FILE_MTIME"
  
  # Determine which metadata to show for comparison (what video tools typically read)
  local metadata_timestamp=""
  local metadata_source=""
  
  if [[ -n "$MEDIA_CREATE_DATE" ]] && [[ "$MEDIA_CREATE_DATE" =~ [0-9] ]]; then
    metadata_timestamp="$(echo "$MEDIA_CREATE_DATE" | sed -E 's/([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}).*/\1/')"
    metadata_source="MediaCreateDate"
  elif [[ -n "$DATETIME_ORIGINAL" ]] && [[ "$DATETIME_ORIGINAL" =~ [0-9] ]]; then
    metadata_timestamp="$(echo "$DATETIME_ORIGINAL" | sed -E 's/([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}).*/\1/')"
    metadata_source="DateTimeOriginal"
  elif [[ -n "$KEYS_CREATION_DATE" ]] && [[ "$KEYS_CREATION_DATE" =~ [0-9] ]]; then
    metadata_timestamp="$(echo "$KEYS_CREATION_DATE" | sed -E 's/([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}).*/\1/')"
    metadata_source="Keys:CreationDate"
  fi
  
  # Format for display
  if [[ -n "$file_timestamp" && -n "$metadata_timestamp" ]]; then
    local file_date_only="${file_timestamp:0:10}"
    local meta_date_only="${metadata_timestamp:0:10}"
    
    # Show both if they differ significantly or file is 1980
    if [[ "$file_date_only" == "1980:01:01" ]] || [[ "$file_date_only" != "$meta_date_only" ]]; then
      echo "$file_timestamp (file), $metadata_timestamp ($metadata_source)"
    else
      echo "$file_timestamp (file and $metadata_source match)"
    fi
  elif [[ -n "$file_timestamp" ]]; then
    echo "$file_timestamp (file)"
  elif [[ -n "$metadata_timestamp" ]]; then
    echo "$metadata_timestamp ($metadata_source)"
  else
    echo "No timestamps found"
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

# CSV-based timezone lookup with DST support
# Returns: offset|abbreviation (e.g., "+0200|CEST")
get_timezone_for_country() {
  local input="$1"
  local date_str="$2"  # Optional: date in format "2025:05:24 12:04:08"
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
  
  # Step 2: Find appropriate timezone for country code and date
  local timezone_line=""
  
  if [[ -n "$date_str" ]]; then
    # Convert date to epoch timestamp for comparison
    local date_epoch
    # Handle both formats: "2025:05:24 12:04:08" and "2025-05-24 12:04:08"
    local normalized_date="$(echo "$date_str" | sed 's/:/-/g' | cut -d' ' -f1)"
    date_epoch=$(date -j -f "%Y-%m-%d" "$normalized_date" "+%s" 2>/dev/null || date -d "$normalized_date" "+%s" 2>/dev/null || echo "0")
    
    if [[ "$date_epoch" -ne 0 ]]; then
      # Find the active timezone for this date
      timezone_line="$(awk -F',' -v cc="$country_code" -v ts="$date_epoch" \
        '$2 == cc && $4 <= ts {line=$0} END {print line}' "$timezone_csv")"
    fi
  fi
  
  # Fallback to most recent entry if no date or date parsing failed
  if [[ -z "$timezone_line" ]]; then
    timezone_line="$(grep ",$country_code," "$timezone_csv" | tail -1)"
  fi
  
  [[ -n "$timezone_line" ]] || return 1  # No timezone data for country
  
  # Step 3: Extract abbreviation and offset
  local tz_abbrev="$(echo "$timezone_line" | cut -d',' -f3)"
  local offset_seconds="$(echo "$timezone_line" | cut -d',' -f5)"
  
  # Convert seconds to +HHMM format
  local offset_str
  if [[ "$offset_seconds" -eq 0 ]]; then
    offset_str="+0000"
  else
    local abs_seconds=$((offset_seconds < 0 ? -offset_seconds : offset_seconds))
    local hours=$((abs_seconds / 3600))
    local minutes=$(((abs_seconds % 3600) / 60))
    local sign=$([[ offset_seconds -lt 0 ]] && echo "-" || echo "+")
    offset_str="$(printf "%s%02d%02d" "$sign" "$hours" "$minutes")"
  fi
  
  # Return both offset and abbreviation
  echo "${offset_str}|${tz_abbrev}"
}

# Get display string for location (includes country name if it's a code)
# Get country name for templating (full name only)
get_country_name() {
  local input="$1"
  local SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local TIMEZONE_DIR="$SCRIPT_DIR/timezones"
  local country_csv="$TIMEZONE_DIR/country.csv"
  
  # If it's a 2-letter code, return full name
  if [[ ${#input} -eq 2 ]]; then
    local country_code="$(echo "$input" | tr '[:lower:]' '[:upper:]')"
    grep "^$country_code," "$country_csv" 2>/dev/null | sed "s/^$country_code,//" | sed 's/^"//;s/"$//' || echo "$input"
  else
    echo "$input"
  fi
}

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

