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

# Variables for timezone info
cli_tz_abbrev=""

# Convert location to timezone if provided
if [[ -n "$cli_location" && -z "$cli_tz" ]]; then
  # We'll get the actual date later, for now just validate the location
  if tz_info=$(get_timezone_for_country "$cli_location" ""); then
    # Parse offset and abbreviation
    cli_tz="$(echo "$tz_info" | cut -d'|' -f1)"
    cli_tz_abbrev="$(echo "$tz_info" | cut -d'|' -f2)"
    # Get location display info from library
    location_display=$(get_location_display "$cli_location")
    echo "🌍 Location: $location_display → Timezone: $cli_tz ($cli_tz_abbrev)"
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
# Returns: offset|source|abbreviation (e.g., "+0200|Keys:CreationDate metadata|CEST")
get_tz_for_file() {
  local file="$1"
  local date_str="$2"  # The timestamp we're processing
  
  # 1. Check DateTimeOriginal for timezone (authoritative source)
  if [[ -n "$DATETIME_ORIGINAL" ]] && [[ "$DATETIME_ORIGINAL" =~ [+-][0-9]{2}:?[0-9]{2}$ ]] && [[ $force_timezone -eq 0 ]]; then
    local tz="$(fix_colon_tz "$(echo "$DATETIME_ORIGINAL" | grep -oE '[+-][0-9]{2}:?[0-9]{2}$')")"
    echo "${tz}|DateTimeOriginal metadata|${tz}"
    return 0
  fi
  
  # 2. Check Keys:CreationDate for timezone (only if DateTimeOriginal doesn't have timezone)
  if [[ -n "$KEYS_CREATION_DATE" ]] && [[ "$KEYS_CREATION_DATE" =~ [+-][0-9]{2}:?[0-9]{2}$ ]] && [[ $force_timezone -eq 0 ]]; then
    local tz="$(fix_colon_tz "$(echo "$KEYS_CREATION_DATE" | grep -oE '[+-][0-9]{2}:?[0-9]{2}$')")"
    echo "${tz}|Keys:CreationDate metadata|${tz}"
    return 0
  fi
  
  # 3. Apply CLI/country timezone with date-aware DST
  if [[ -n "$cli_location" ]]; then
    # Get timezone for specific date to handle DST correctly
    if tz_info=$(get_timezone_for_country "$cli_location" "$date_str"); then
      local tz="$(echo "$tz_info" | cut -d'|' -f1)"
      local abbrev="$(echo "$tz_info" | cut -d'|' -f2)"
      local location_display=$(get_location_display "$cli_location")
      echo "${tz}|--location $cli_location ($location_display)|${abbrev}"
      return 0
    fi
  elif [[ -n "$cli_tz" ]]; then
    local tz="$(fix_colon_tz "$cli_tz")"
    echo "${tz}|--timezone ${tz}|${tz}"
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
  local best_timestamp="$(cat /tmp/timestamp_result_$$)"
  rm -f /tmp/timestamp_result_$$
  local dt_source="$TIMESTAMP_SOURCE"
  
  log_verbose "  Best timestamp: $best_timestamp (source: $dt_source)"
  
  # Get timezone for this file
  local tz_info tz tz_source tz_abbrev
  if ! tz_info="$(get_tz_for_file "$file" "$best_timestamp")"; then
    echo "❌ $base: No timezone (use --timezone or --location). Aborting." >&2
    return 1
  fi
  
  # Parse the timezone info (offset|source|abbreviation)
  IFS='|' read -r tz tz_source tz_abbrev <<< "$tz_info"
  
  # Format timezone source for display - only show abbreviation if it's meaningful (not same as offset)
  if [[ -n "$tz_abbrev" && "$tz_abbrev" != "$tz" ]]; then
    tz_source="${tz_source} (${tz_abbrev})"
  elif [[ "$tz_source" =~ "metadata" ]]; then
    # For metadata sources, show the offset in the source
    tz_source="${tz_source} (${tz})"
  fi
  
  log_verbose "  Timezone: $tz (source: $tz_source)"
  
  local corrected_timestamp="${best_timestamp}${tz}"
  log_verbose "  Corrected timestamp: $corrected_timestamp"
  
  # Convert to UTC
  local utc_time="$(to_utc "$corrected_timestamp")"
  log_verbose "  UTC time: $utc_time"
  
  # Format original timestamps for display (using raw data from get_best_timestamp)
  local original_display="$(format_original_timestamps)"
  log_verbose "  Original: $original_display"
  
  # Determine what changes are needed using raw file timestamp
  local file_timestamp="$FILE_BIRTHTIME"
  [[ -z "$file_timestamp" && -n "$FILE_MTIME" ]] && file_timestamp="$FILE_MTIME"
  local change_desc="$(determine_change_needed "$file_timestamp" "$corrected_timestamp")"
  local needs_update=1
  [[ "$change_desc" == "No change" ]] && needs_update=0
  
  # Check if CreationDate needs updating (either FCP fix or restoration)
  # Check if CreateDate/ModifyDate need timezone fixing or CreationDate needs removal
  local metadata_change=""
  local createdate_has_tz=0
  local modifydate_has_tz=0
  local creation_exists=0
  
  # Check if CreateDate has timezone
  if [[ -n "$CREATE_DATE" ]] && [[ "$CREATE_DATE" =~ [+-][0-9]{2}:?[0-9]{2}$ ]]; then
    createdate_has_tz=1
  fi
  
  # Check if ModifyDate has timezone
  if [[ -n "$MODIFY_DATE" ]] && [[ "$MODIFY_DATE" =~ [+-][0-9]{2}:?[0-9]{2}$ ]]; then
    modifydate_has_tz=1
  fi
  
  # Check if CreationDate exists
  if [[ -n "$KEYS_CREATION_DATE" ]]; then
    creation_exists=1
  fi
  
  # Determine what metadata changes are needed
  if [[ $createdate_has_tz -eq 0 || $modifydate_has_tz -eq 0 || $creation_exists -eq 1 ]]; then
    local changes=()
    [[ $createdate_has_tz -eq 0 ]] && changes+=("CreateDate timezone")
    [[ $modifydate_has_tz -eq 0 ]] && changes+=("ModifyDate timezone")
    [[ $creation_exists -eq 1 ]] && changes+=("Remove CreationDate")
    
    metadata_change="Metadata: $(IFS=', '; echo "${changes[*]}")"
    needs_update=1
  fi
  
  # Display comparison info
  printf "\033[36m🔍 %s\033[0m\n" "$base"
  printf "📅 Original : %s\n" "$original_display"
  printf "⏱️ Corrected: %s (from %s, tz: %s)\n" "$corrected_timestamp" "$dt_source" "$tz_source"
  printf "🌐 UTC      : %s UTC\n" "$utc_time"
  
  # Combine file timestamp and metadata changes
  local combined_change="$change_desc"
  if [[ -n "$metadata_change" ]]; then
    if [[ "$change_desc" == "No change" ]]; then
      combined_change="$metadata_change"
    else
      combined_change="$change_desc, $metadata_change"
    fi
  fi
  
  # Show change status with dry run indicator if not applying
  if [[ $needs_update -eq 1 && $apply -eq 0 ]]; then
    printf "📊 Change   : %s (DRY RUN)\n" "$combined_change"
  else
    printf "📊 Change   : %s\n" "$combined_change"
  fi
  
  
  # Update metadata and file timestamps if changes needed and in apply mode
  if [[ $needs_update -eq 1 && $apply -eq 1 ]]; then
    log_verbose "  Updating metadata..."
    set_file_timestamps "$file" "$corrected_timestamp" "$utc_time"
    
    # Don't update file system timestamps - FCP reads metadata, not file timestamps
    # Updating file timestamps can cause timezone confusion in FCP
    if false && [[ "$change_desc" != "No change" ]]; then
      log_verbose "  Updating file system timestamps..."
      log_verbose "  Corrected timestamp for file system: $corrected_timestamp"
      
      # Convert timestamp for SetFile (MM/DD/YYYY HH:MM:SS format)
      local setfile_time
      if setfile_time="$(date -j -f "%Y:%m:%d %H:%M:%S %z" "$corrected_timestamp" "+%m/%d/%Y %H:%M:%S" 2>/dev/null)"; then
        log_verbose "  SetFile timestamp: $setfile_time"
        SetFile -d "$setfile_time" "$file" 2>/dev/null || true
      else
        log_verbose "  SetFile date conversion failed for: $corrected_timestamp"
      fi
      
      # Convert timestamp for touch (YYYYMMDDHHMM.SS format)  
      local touch_time
      if touch_time="$(date -j -f "%Y:%m:%d %H:%M:%S %z" "$corrected_timestamp" "+%Y%m%d%H%M.%S" 2>/dev/null)"; then
        log_verbose "  touch timestamp: $touch_time"
        touch -t "$touch_time" "$file" 2>/dev/null || true
      else
        log_verbose "  touch date conversion failed for: $corrected_timestamp"
      fi
    fi
    
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