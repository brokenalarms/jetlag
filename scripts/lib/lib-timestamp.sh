#!/bin/bash
# Library - Timezone lookup functions
# Not executable directly - source this file from other scripts
#
# Only caller: batch-fix-media-timestamp.sh (display-only timezone info).
# All timestamp fixing logic now lives in the Python pipeline.

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
    local sign=$([[ $offset_seconds -lt 0 ]] && echo "-" || echo "+")
    offset_str="$(printf "%s%02d%02d" "$sign" "$hours" "$minutes")"
  fi

  # Return both offset and abbreviation
  echo "${offset_str}|${tz_abbrev}"
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
