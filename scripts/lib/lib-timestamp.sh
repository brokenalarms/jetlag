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
MEDIA_MODIFY_DATE=""
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
  MEDIA_MODIFY_DATE=""
  KEYS_CREATION_DATE=""
  FILENAME_DATE=""
  CREATE_DATE=""
  MODIFY_DATE=""

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
  # Use -fast to skip some metadata parsing for better performance with large files
  local metadata_output
  metadata_output=$(exiftool -fast2 -s -DateTimeOriginal -QuickTime:MediaCreateDate -QuickTime:MediaModifyDate -Keys:CreationDate -CreateDate -ModifyDate "$file" 2>/dev/null || true)


  # Parse the metadata output
  if [[ "$metadata_output" =~ DateTimeOriginal[[:space:]]*:[[:space:]]*([-0-9: +:]+) ]]; then
    DATETIME_ORIGINAL="${BASH_REMATCH[1]}"
  fi
  if [[ "$metadata_output" =~ MediaCreateDate[[:space:]]*:[[:space:]]*([-0-9: +:]+) ]]; then
    MEDIA_CREATE_DATE="${BASH_REMATCH[1]}"
  fi
  if [[ "$metadata_output" =~ MediaModifyDate[[:space:]]*:[[:space:]]*([-0-9: +:]+) ]]; then
    MEDIA_MODIFY_DATE="${BASH_REMATCH[1]}"
  fi
  # Use more specific patterns to avoid conflicts
  if [[ "$metadata_output" =~ ^CreateDate[[:space:]]*:[[:space:]]*([-0-9: +:]+)$ ]] || \
     [[ "$metadata_output" =~ $'\n'CreateDate[[:space:]]*:[[:space:]]*([-0-9: +:]+)($|$'\n') ]]; then
    CREATE_DATE="${BASH_REMATCH[1]}"
  fi
  if [[ "$metadata_output" =~ CreationDate[[:space:]]*:[[:space:]]*([-0-9: +:]+) ]]; then
    KEYS_CREATION_DATE="${BASH_REMATCH[1]}"
  fi
  # Match ModifyDate but not MediaModifyDate (use word boundary or start of line)
  if [[ "$metadata_output" =~ ^ModifyDate[[:space:]]*:[[:space:]]*([-0-9: +:]+)$ ]] || \
     [[ "$metadata_output" =~ $'\n'ModifyDate[[:space:]]*:[[:space:]]*([-0-9: +:]+)($|$'\n') ]]; then
    MODIFY_DATE="${BASH_REMATCH[1]}"
  fi

  return 0
}

# Set timestamps for a file (metadata and file system) based on what needs updating
# Usage: set_file_timestamps "/path/to/file.mp4" "2024:01:01 12:00:00+0100" "2024:01:01 11:00:00"
# Note: Uses global variables from get_file_timestamps() to determine what needs updating
set_file_timestamps() {
  local file="$1"
  local corrected_timestamp="$2"  # Corrected timestamp with timezone (e.g., "2024:01:01 12:00:00+0100")
  local utc_time="$3"             # UTC time (e.g., "2024:01:01 11:00:00")

  # Extract just the datetime without timezone
  local timestamp_no_tz="${corrected_timestamp:0:19}"

  # Build exiftool arguments array - only add changes that are needed
  local exiftool_args=()
  local has_metadata_changes=0

  # Set DateTimeOriginal if missing (preserves original shooting time with timezone)
  if [[ -z "$DATETIME_ORIGINAL" ]]; then
    exiftool_args+=("-DateTimeOriginal=$corrected_timestamp")
    has_metadata_changes=1
  fi

  # Set CreateDate with timezone if it needs changing
  if [[ -z "$CREATE_DATE" ]] || [[ "$CREATE_DATE" != "$corrected_timestamp" ]]; then
    exiftool_args+=("-CreateDate=$corrected_timestamp")
    has_metadata_changes=1
  fi

  # Set ModifyDate with timezone if it needs changing
  if [[ -z "$MODIFY_DATE" ]] || [[ "$MODIFY_DATE" != "$corrected_timestamp" ]]; then
    exiftool_args+=("-ModifyDate=$corrected_timestamp")
    has_metadata_changes=1
  fi

  # Fix MediaCreateDate/MediaModifyDate if they need changing
  # These should be UTC equivalent of shooting time (no timezone)
  local utc_no_tz="${utc_time:0:19}"
  if [[ -z "$MEDIA_CREATE_DATE" ]] || [[ "$MEDIA_CREATE_DATE" != "$utc_no_tz" ]]; then
    exiftool_args+=("-QuickTime:MediaCreateDate=$utc_no_tz")
    has_metadata_changes=1
  fi
  if [[ -z "$MEDIA_MODIFY_DATE" ]] || [[ "$MEDIA_MODIFY_DATE" != "$utc_no_tz" ]]; then
    exiftool_args+=("-QuickTime:MediaModifyDate=$utc_no_tz")
    has_metadata_changes=1
  fi

  # Set FileModifyDate/FileAccessDate with timezone (EXIF metadata fields)
  exiftool_args+=("-FileModifyDate=$corrected_timestamp")
  exiftool_args+=("-FileAccessDate=$corrected_timestamp")
  has_metadata_changes=1

  # Remove CreationDate if it exists (FCP misinterprets this field)
  if [[ -n "$KEYS_CREATION_DATE" ]]; then
    exiftool_args+=("-Keys:CreationDate=")
    has_metadata_changes=1
  fi

  # Only call exiftool if there are metadata changes to make
  if [[ $has_metadata_changes -eq 1 ]]; then
    exiftool_args=("-overwrite_original" "${exiftool_args[@]}")
    exiftool -fast2 "${exiftool_args[@]}" "$file" >/dev/null 2>&1
  fi

  return 0
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
