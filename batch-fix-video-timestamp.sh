#!/bin/bash
# batch-fix-video-timestamps.sh  
# Batch processes video files in current directory using fix-video-timestamp.sh
# Supports: MP4, MOV, INSV (Insta360 raw), LRV (low-res video) files
# Usage: ./batch-fix-video-timestamps.sh [--apply] [--only-insta] [--country COUNTRY | --timezone +HHMM] [--verbose]

set -euo pipefail
IFS=$'\n\t'

apply=0
verbose=0
only_insta=0
args=()

# Get script directory 
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/lib-timestamp.sh"

# Check if fix-video-timestamp.sh exists
SINGLE_SCRIPT="$SCRIPT_DIR/fix-video-timestamp.sh"
[[ -x "$SINGLE_SCRIPT" ]] || { 
  echo "ERROR: $SINGLE_SCRIPT not found or not executable" >&2
  exit 1
}

# ---------- args ----------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) 
      apply=1
      args+=("$1")
      shift ;;
    --verbose|-v) 
      verbose=1
      args+=("$1")
      shift ;;
    --only-insta)
      only_insta=1
      shift ;;
    --timezone)
      args+=("$1")
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --timezone needs +HHMM or +HH:MM"; exit 1; }
      args+=("$1")
      shift ;;
    --location)
      args+=("$1")
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --location requires a location name/code"; exit 1; }
      args+=("$1")
      shift ;;
    --country)
      # Legacy support - map to --location
      args+=("--location")
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --country requires a country name/code"; exit 1; }
      args+=("$1")
      shift ;;
    --force-timezone)
      args+=("$1")
      shift ;;
    --help|-h) 
      echo "Usage: batch-fix-video-timestamps.sh [OPTIONS]"
      echo "Options:"
      echo "  --apply         Apply changes to all files (default: dry run)"
      echo "  --only-insta    Only process VID_* files (Insta360 videos)"
      echo "  --verbose, -v   Show detailed processing info"  
      echo "  --timezone TZ   Use specific timezone (+HHMM format)"
      echo "  --location NAME Use location name/code for timezone lookup"
      echo "  --country NAME  [DEPRECATED] Use --location instead"
      echo "  --force-timezone Override existing timezone metadata"
      echo "  --help, -h      Show this help"
      exit 0 ;;
    *) 
      echo "ERROR: Unknown option $1" >&2
      echo "Use --help for usage information" >&2
      exit 1 ;;
  esac
done

# ---------- main ----------
# Show timezone info if location/timezone args are provided
for (( i=0; i<${#args[@]}; i++ )); do
  if [[ "${args[i]}" == "--location" && $((i+1)) < ${#args[@]} ]]; then
    location_code="${args[$((i+1))]}"
    if timezone=$(get_timezone_for_country "$location_code" 2>/dev/null); then
      location_display=$(get_location_display "$location_code")
      echo "🌍 Using location: $location_display → Timezone: $timezone"
    fi
    break
  elif [[ "${args[i]}" == "--timezone" && $((i+1)) < ${#args[@]} ]]; then
    echo "🕐 Using timezone: ${args[$((i+1))]}"
    break
  fi
done

echo "🕓 Scanning video files..."

file_count=0
processed_count=0
failed_count=0
skipped_count=0

# Build find pattern based on --only-insta flag
if [[ $only_insta -eq 1 ]]; then
  echo "📹 Looking for Insta360 videos (VID_* files only)"
  file_pattern="-name 'VID_*.mp4' -o -name 'VID_*.MP4' -o -name 'VID_*.mov' -o -name 'VID_*.MOV' -o -name 'VID_*.insv' -o -name 'VID_*.INSV' -o -name 'VID_*.lrv' -o -name 'VID_*.LRV'"
else
  echo "📹 Looking for all video files (*.mp4, *.mov, *.insv, *.lrv)"
  file_pattern="-name '*.mp4' -o -name '*.MP4' -o -name '*.mov' -o -name '*.MOV' -o -name '*.insv' -o -name '*.INSV' -o -name '*.lrv' -o -name '*.LRV'"
fi

# Process files

while IFS= read -r -d '' file; do
  file_count=$((file_count + 1))
  
  # Run single script directly - let it handle its own output
  if [[ ${#args[@]} -gt 0 ]]; then
    "$SINGLE_SCRIPT" "$file" "${args[@]}"
    exit_code=$?
  else
    "$SINGLE_SCRIPT" "$file"
    exit_code=$?
  fi
  
  if [[ $exit_code -eq 0 ]]; then
    processed_count=$((processed_count + 1))
  else
    failed_count=$((failed_count + 1))
    echo "⚠️ Failed to process: $(basename "$file")"
  fi
done < <(eval "find . -type f \\( $file_pattern \\) -print0")

# Always show summary even if no files processed
if [[ $file_count -eq 0 ]]; then
  echo "No matching files found."
  exit 0
fi

# Summary
echo ""
echo "=========================================="
echo "📊 BATCH PROCESSING SUMMARY"
echo "----------------------------------------"
echo "Total files found: $file_count"
if [[ $skipped_count -gt 0 ]]; then
  echo "Already correct: $skipped_count"
fi
needs_changes=$((processed_count - skipped_count))
if [[ $needs_changes -gt 0 ]]; then
  echo "Needs changes: $needs_changes"
fi
if [[ $failed_count -gt 0 ]]; then
  echo "Failed: $failed_count"
fi

if [[ $needs_changes -eq 0 ]]; then
  echo "✅ All files already have correct timestamps."
elif [[ $apply -eq 1 ]]; then
  echo "✅ Batch timestamp processing complete - changes applied to $needs_changes file(s)."
else  
  echo "✅ Batch timestamp processing complete - DRY RUN."
  echo "   Use --apply to update $needs_changes file(s)."
fi

# Exit with error if any files failed
[[ $failed_count -eq 0 ]] || exit 1