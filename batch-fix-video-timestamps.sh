#!/bin/bash
# batch-fix-video-timestamps.sh  
# Batch processes video files in current directory using fix-video-timestamp.sh
# Usage: ./batch-fix-video-timestamps.sh [--apply] [--only-insta] [--country COUNTRY | --timezone +HHMM] [--verbose]

set -euo pipefail
IFS=$'\n\t'

apply=0
verbose=0
only_insta=0
args=()

# Get script directory 
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
    --country)
      args+=("$1")
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --country requires a country name/code"; exit 1; }
      args+=("$1")
      shift ;;
    --help|-h) 
      echo "Usage: batch-fix-video-timestamps.sh [OPTIONS]"
      echo "Options:"
      echo "  --apply         Apply changes to all files (default: dry run)"
      echo "  --only-insta    Only process VID_* files (Insta360 videos)"
      echo "  --verbose, -v   Show detailed processing info"  
      echo "  --timezone TZ   Use specific timezone (+HHMM format)"
      echo "  --country NAME  Use country name/code for timezone lookup"
      echo "  --help, -h      Show this help"
      exit 0 ;;
    *) 
      echo "ERROR: Unknown option $1" >&2
      echo "Use --help for usage information" >&2
      exit 1 ;;
  esac
done

# ---------- main ----------
echo "🕓 Scanning video files..."

file_count=0
processed_count=0
failed_count=0

# Build find pattern based on --only-insta flag
if [[ $only_insta -eq 1 ]]; then
  echo "📹 Looking for Insta360 videos (VID_* files only)"
  file_pattern="-name 'VID_*.mp4' -o -name 'VID_*.MP4' -o -name 'VID_*.mov' -o -name 'VID_*.MOV'"
else
  echo "📹 Looking for all video files (*.mp4, *.mov)"
  file_pattern="-name '*.mp4' -o -name '*.MP4' -o -name '*.mov' -o -name '*.MOV'"
fi

# Process files
while IFS= read -r -d '' file; do
  file_count=$((file_count + 1))
  
  echo "Processing file $file_count: $(basename "$file")"
  echo "----------------------------------------"
  
  if "$SINGLE_SCRIPT" "$file" "${args[@]}"; then
    processed_count=$((processed_count + 1))
  else
    failed_count=$((failed_count + 1))
    echo "⚠️ Failed to process: $(basename "$file")"
  fi
  
  echo
done < <(eval "find . -type f \\( $file_pattern \\) -print0")

# Summary
echo "=========================================="
echo "📊 BATCH PROCESSING SUMMARY"
echo "----------------------------------------"
echo "Total files found: $file_count"
echo "Successfully processed: $processed_count"
if [[ $failed_count -gt 0 ]]; then
  echo "Failed: $failed_count"
fi

if [[ $apply -eq 1 ]]; then
  echo "✅ Batch timestamp processing complete - changes applied to $processed_count file(s)."
else  
  echo "✅ Batch timestamp processing complete - DRY RUN (no changes made)."
  echo "   Use --apply to actually update the files."
fi

# Exit with error if any files failed
[[ $failed_count -eq 0 ]] || exit 1