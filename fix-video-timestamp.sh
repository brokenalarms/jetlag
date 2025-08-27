#!/bin/bash
# fix-video-timestamp-v2.sh
# Simplified version using the new library functions
# Fixes a single video file timestamp using filename patterns or EXIF data
# Usage: ./fix-video-timestamp-v2.sh VIDEO_FILE [--apply] [--country COUNTRY | --timezone +HHMM] [--verbose]

set -euo pipefail
IFS=$'\n\t'

apply=0
verbose=0
cli_tz=""
cli_location=""
force_timezone=0
video_file=""

# Get script directory and source libraries
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/lib-timestamp.sh"

# ---------- args ----------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) apply=1; shift ;;
    --verbose|-v) verbose=1; shift ;;
    --force-timezone) force_timezone=1; shift ;;
    --timezone)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --timezone needs +HHMM or +HH:MM"; exit 1; }
      cli_tz="$1"; shift ;;
    --location)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --location requires a location name/code"; exit 1; }
      cli_location="$1"; shift ;;
    --help|-h) 
      echo "Usage: fix-video-timestamp.sh VIDEO_FILE [OPTIONS]"
      echo "Options:"
      echo "  --apply         Apply changes (default: dry run)"
      echo "  --verbose, -v   Show detailed processing info"  
      echo "  --timezone TZ   Use specific timezone (+HHMM format)"
      echo "  --location NAME Use location name/code for timezone lookup"
      echo "  --force-timezone Override existing timezone metadata"
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

# Convert location to timezone if provided
if [[ -n "$cli_location" && -z "$cli_tz" ]]; then
  if cli_tz=$(get_timezone_for_country "$cli_location"); then
    # Get location display info from library
    location_display=$(get_location_display "$cli_location")
    echo "🌍 Location: $location_display → Timezone: $cli_tz"
  else
    echo "ERROR: Unknown location '$cli_location'." >&2
    exit 1
  fi
fi

# ---------- helpers ----------
log_verbose() {
  [[ $verbose -eq 1 ]] && echo "$@" >&2
}

# Get timezone for this file
get_tz_for_file() {
  local file="$1"
  local dir="$(dirname "$file")"
  
  # 1. Check for local timezone.txt file (explicit override)
  if [[ -f "$dir/timezone.txt" ]]; then
    local tz="$(head -n1 "$dir/timezone.txt")"
    chflags hidden "$dir/timezone.txt" 2>/dev/null || true
    echo "$(fix_colon_tz "$tz")"
    return 0
  fi
  
  # 2. Check if file already has timezone in metadata (respect existing unless forced)
  if [[ -n "$DATETIME_ORIGINAL" ]] && [[ "$DATETIME_ORIGINAL" =~ [+-][0-9]{2}:?[0-9]{2}$ ]] && [[ $force_timezone -eq 0 ]]; then
    echo "$(fix_colon_tz "$(echo "$DATETIME_ORIGINAL" | grep -oE '[+-][0-9]{2}:?[0-9]{2}$')")"
    return 0
  fi
  
  # 3. Apply CLI/country timezone
  if [[ -n "$cli_tz" ]]; then
    echo "$(fix_colon_tz "$cli_tz")"
    return 0
  fi
  
  return 1
}

# ---------- main processing ----------
process_video_file() {
  local file="$1"
  local base="$(basename "$file")"
  
  log_verbose "Processing: $file"
  
  # Get the best timestamp to use (function knows the right priority for each file type)
  # Note: Can't use command substitution as it runs in subshell and loses global variables
  get_best_timestamp "$file" > /tmp/timestamp_result_$$
  local local_dt="$(cat /tmp/timestamp_result_$$)"
  rm -f /tmp/timestamp_result_$$
  local dt_source="$TIMESTAMP_SOURCE"
  
  log_verbose "  Local datetime: $local_dt (source: $dt_source)"
  
  # Get timezone for this file
  local tz tz_source
  if ! tz="$(get_tz_for_file "$file")"; then
    echo "❌ $base: No timezone (use --timezone or timezone.txt). Aborting." >&2
    return 1
  fi
  
  # Determine timezone source for display
  if [[ -f "$(dirname "$file")/timezone.txt" ]]; then
    tz_source="timezone.txt"
  elif [[ -n "$DATETIME_ORIGINAL" ]] && [[ "$DATETIME_ORIGINAL" =~ [+-][0-9]{2}:?[0-9]{2}$ ]] && [[ $force_timezone -eq 0 ]]; then
    tz_source="existing metadata"
  elif [[ $force_timezone -eq 1 ]]; then
    if [[ -n "$cli_location" ]]; then
      tz_source="--location $cli_location (forced)"
    else
      tz_source="--timezone $cli_tz (forced)"
    fi
  else
    if [[ -n "$cli_location" ]]; then
      tz_source="--location $cli_location"
    else
      tz_source="--timezone $cli_tz"
    fi
  fi
  
  log_verbose "  Timezone: $tz (source: $tz_source)"
  
  local local_with_tz="${local_dt}${tz}"
  log_verbose "  Local with TZ: $local_with_tz"
  
  # Convert to UTC
  local utc_time="$(to_utc "$local_with_tz")"
  log_verbose "  UTC time: $utc_time"
  
  # Get original metadata for comparison
  local comparison_data="$(get_timestamp_comparison "$file")"
  local original_display
  IFS='|' read -r file_ts meta_ts meta_src differs <<< "$comparison_data"
  
  if [[ "$differs" == "true" ]]; then
    original_display="$file_ts (file) vs $meta_ts ($meta_src)"
  else
    original_display="${file_ts:-$meta_ts} (${meta_src:-file creation date})"
  fi
  log_verbose "  Original: $original_display"
  
  # Determine what changes are needed
  local change_desc="$(determine_change_needed "$original_display" "$local_with_tz")"
  local needs_update=1
  [[ "$change_desc" == "No change" ]] && needs_update=0
  
  # Display comparison info
  printf "\033[36m🔍 %s\033[0m\n" "$base"
  printf "📅 Original : %s\n" "$original_display"
  printf "⏱️ Corrected: %s (from %s, tz: %s)\n" "$local_with_tz" "$dt_source" "$tz_source"
  printf "🌐 UTC      : %s UTC\n" "$utc_time"
  
  # Show change status with dry run indicator if not applying
  if [[ $needs_update -eq 1 && $apply -eq 0 ]]; then
    printf "📊 Change   : %s (DRY RUN)\n" "$change_desc"
  else
    printf "📊 Change   : %s\n" "$change_desc"
  fi
  
  # Update metadata if changes needed and in apply mode
  if [[ $needs_update -eq 1 && $apply -eq 1 ]]; then
    log_verbose "  Updating metadata..."
    set_file_timestamps "$file" "$local_with_tz" "$utc_time"
    log_verbose "  ✅ Metadata updated"
    echo "   ✅ Applied"
  fi
  
  echo  # Empty line for readability
  return 0
}

# ---------- main ----------
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