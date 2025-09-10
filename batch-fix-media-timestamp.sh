#!/bin/bash
# batch-fix-media-timestamps.sh  
# Batch processes media files (photos and videos) in current directory using fix-media-timestamp.sh
# Supports: Photos (JPG, JPEG, PNG, HEIC, RAW, etc.) and Videos (MP4, MOV, INSV, LRV, etc.)
# Usage: ./batch-fix-media-timestamps.sh [--apply] [--only-insta] [--country COUNTRY | --timezone +HHMM]

set -euo pipefail
IFS=$'\n\t'

apply=0
only_insta=0
args=()

# Get script directory 
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/lib-timestamp.sh"

# Check if main file exists
SINGLE_SCRIPT="$SCRIPT_DIR/fix-media-timestamp.sh"
[[ -x "$SINGLE_SCRIPT" ]] || { 
  echo "ERROR: $SINGLE_SCRIPT not found or not executable" >&2
  exit 1
}

# ---------- args ----------
# Parse arguments - pass most through, but handle batch-specific ones
while [[ $# -gt 0 ]]; do
  case "$1" in
    --only-insta)
      only_insta=1
      shift ;;
    --apply) 
      apply=1
      args+=("$1")
      shift ;;
    --help|-h) 
      echo "Usage: batch-fix-media-timestamps.sh [OPTIONS]"
      echo "Options:"
      echo "  --apply         Apply changes to all files (default: dry run)"
      echo "  --only-insta    Only process VID_* files (Insta360 videos)"
      echo ""
      echo "All other options are passed through to fix-media-timestamp.sh:"
      echo "  --timezone TZ   Use specific timezone (+HHMM format)"
      echo "  --location NAME Use location name/code for timezone lookup"
      echo "  --force-timezone Override existing timezone metadata"
      echo "  --help, -h      Show this help"
      exit 0 ;;
    --timezone|--location|--country)
      # Arguments that need a value
      args+=("$1")
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: $1 requires a value"; exit 1; }
      args+=("$1")
      shift ;;
    --*)
      # Pass through all other options
      args+=("$1")
      shift ;;
    *) 
      echo "ERROR: Unexpected argument $1" >&2
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

echo "🕓 Scanning media files..."

file_count=0
processed_count=0
failed_count=0
skipped_count=0

# Build find pattern based on --only-insta flag
if [[ $only_insta -eq 1 ]]; then
  echo "📹 Looking for Insta360 videos (VID_* files only)"
  file_pattern="-name 'VID_*.mp4' -o -name 'VID_*.MP4' -o -name 'VID_*.mov' -o -name 'VID_*.MOV' -o -name 'VID_*.insv' -o -name 'VID_*.INSV' -o -name 'VID_*.lrv' -o -name 'VID_*.LRV'"
else
  echo "📹 Looking for all media files (photos and videos)"
  # Common video extensions
  file_pattern="-iname '*.mp4' -o -iname '*.mov' -o -iname '*.avi' -o -iname '*.mkv' -o -iname '*.m4v'"
  file_pattern="$file_pattern -o -iname '*.insv' -o -iname '*.lrv'"
  # Common photo extensions
  file_pattern="$file_pattern -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png'"
  file_pattern="$file_pattern -o -iname '*.heic' -o -iname '*.heif'"
  # RAW photo formats
  file_pattern="$file_pattern -o -iname '*.raw' -o -iname '*.arw' -o -iname '*.cr2' -o -iname '*.cr3'"
  file_pattern="$file_pattern -o -iname '*.nef' -o -iname '*.dng' -o -iname '*.orf' -o -iname '*.rw2'"
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