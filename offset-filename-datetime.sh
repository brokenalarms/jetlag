#!/bin/bash
# offset-filename-datetime.sh
# Corrects Insta360 files that were shot with wrong date/time settings
# Offsets both the filename and all metadata timestamps to correct values
# Usage: ./offset-filename-datetime.sh --base <misdated_file> --correct <YYYYMMDD_HHMMSS> [--filter PREFIX] [--apply] [--overwrite]

set -euo pipefail
IFS=$'\n\t'

# Get script directory and source libraries
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/lib-common.sh"
source "$SCRIPT_DIR/lib/lib-timestamp.sh"

# Initialize variables
apply_changes=0
overwrite_in_place=0
match_count=0
skipped_count=0
base_file=""
correct_str=""
filter_prefix=""
verbose=0

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --base) base_file="$2"; shift 2 ;;
    --correct) correct_str="$2"; shift 2 ;;
    --filter) filter_prefix="$2"; shift 2 ;;
    --apply) apply_changes=1; shift ;;
    --overwrite) overwrite_in_place=1; shift ;;
    --verbose|-v) verbose=1; shift ;;
    --help|-h) 
      echo "Usage: $0 --base <misdated_file> --correct <YYYYMMDD_HHMMSS> [OPTIONS]"
      echo ""
      echo "Corrects timestamps for Insta360 files shot with wrong date/time settings"
      echo ""
      echo "Required:"
      echo "  --base FILE     Reference file with wrong datetime"
      echo "  --correct TIME  Correct datetime for that file (YYYYMMDD_HHMMSS)"
      echo ""
      echo "Options:"
      echo "  --filter PREFIX Filter files by date prefix (optional)"
      echo "  --apply         Apply changes (default: dry run)"
      echo "  --overwrite     Rename files in place (default: copy to ./corrected/)"
      echo "  --verbose, -v   Show detailed processing info"
      echo "  --help, -h      Show this help"
      exit 0
      ;;
    *) echo "ERROR: Unknown argument: $1" >&2; exit 1 ;;
  esac
done

# Validate required arguments
if [[ -z "$base_file" || -z "$correct_str" ]]; then
  echo "ERROR: --base and --correct are required" >&2
  echo "Use --help for usage information" >&2
  exit 1
fi

if ! [[ "$correct_str" =~ ^[0-9]{8}_[0-9]{6}$ ]]; then
  echo "ERROR: --correct must be in format YYYYMMDD_HHMMSS (e.g., 20250505_130334)" >&2
  exit 1
fi

if [[ "$overwrite_in_place" -eq 0 ]]; then
  mkdir -p corrected
fi

# Parse base and correct timestamps
base_full=$(echo "$base_file" | grep -oE '[0-9]{8}_[0-9]{6}')
if [[ -z "$base_full" ]]; then
  echo "ERROR: Could not extract timestamp from base file: $base_file" >&2
  exit 1
fi

base_date="${base_full%_*}"
base_time="${base_full#*_}"
correct_date="${correct_str%_*}"
correct_time="${correct_str#*_}"

# Calculate offset in seconds
base_epoch=$(date -j -f "%Y%m%d%H%M%S" "${base_date}${base_time}" +%s 2>/dev/null) || {
  echo "ERROR: Invalid base timestamp: ${base_date}_${base_time}" >&2
  exit 1
}

correct_epoch=$(date -j -f "%Y%m%d%H%M%S" "${correct_date}${correct_time}" +%s 2>/dev/null) || {
  echo "ERROR: Invalid correct timestamp: ${correct_date}_${correct_time}" >&2
  exit 1
}

offset_sec=$((correct_epoch - base_epoch))

# Calculate human-readable offset
days_offset=$((offset_sec / 86400))
hours_offset=$(( (offset_sec % 86400) / 3600 ))
minutes_offset=$(( (offset_sec % 3600) / 60 ))
seconds_offset=$((offset_sec % 60))

# Handle negative offsets for display
if [[ $offset_sec -ge 0 ]]; then
  offset_sign="+"
  abs_days=$days_offset
  abs_hours=$hours_offset
  abs_minutes=$minutes_offset
  abs_seconds=$seconds_offset
else
  offset_sign="-"
  abs_days=$((-days_offset))
  abs_hours=$((-hours_offset))
  abs_minutes=$((-minutes_offset))
  abs_seconds=$((-seconds_offset))
fi

# Display configuration (concise)
echo "📸 Offset: ${offset_sign}${abs_days}d ${abs_hours}h ${abs_minutes}m ${abs_seconds}s | ${base_date:0:4}-${base_date:4:2}-${base_date:6:2} ${base_time:0:2}:${base_time:2:2}:${base_time:4:2} → ${correct_date:0:4}-${correct_date:4:2}-${correct_date:6:2} ${correct_time:0:2}:${correct_time:2:2}:${correct_time:4:2}"
if [[ -n "$filter_prefix" ]]; then
  echo "🔍 Filter: $filter_prefix"
fi
echo "💾 Mode: $([[ $apply_changes -eq 1 ]] && echo "APPLY" || echo "DRY RUN")"
echo ""

# Helper function to check if file needs changes
needs_changes() {
  local file="$1"
  local expected_name="$2"
  
  # Check if filename already matches expected
  if [[ "$(basename "$file")" == "$expected_name" ]]; then
    return 1  # No changes needed
  fi
  
  return 0  # Changes needed
}

# Process all matching files
for ext in insv lrv mp4 mov INSV LRV MP4 MOV; do
  while IFS= read -r -d '' file; do
    # Check if file exists
    [[ -f "$file" ]] || continue
    
    # Apply filter if specified
    if [[ -n "$filter_prefix" ]]; then
      [[ $file == *_${filter_prefix}* ]] || continue
    fi

    # Parse filename components - support VID_, LRV_, IMG_ prefixes
    prefix=""
    orig_date=""
    orig_time=""
    sequence=""
    base_name="$(basename "$file")"
    
    if [[ "$base_name" =~ ^(VID|LRV|IMG)_([0-9]{8})_([0-9]{6})_[0-9]{2}_([0-9]+)\. ]]; then
      prefix="${BASH_REMATCH[1]}"
      orig_date="${BASH_REMATCH[2]}"
      orig_time="${BASH_REMATCH[3]}"
      sequence="${BASH_REMATCH[4]}"
    else
      continue  # Skip files that don't match pattern
    fi

    # Calculate corrected timestamp
    timestamp_input="${orig_date}${orig_time}"
    epoch=$(date -j -f "%Y%m%d%H%M%S" "$timestamp_input" +%s 2>/dev/null) || {
      echo "❌ Date parse failed: $file"
      continue
    }

    corrected_epoch=$((epoch + offset_sec))
    new_date=$(date -j -r "$corrected_epoch" "+%Y%m%d")
    new_time=$(date -j -r "$corrected_epoch" "+%H%M%S")
    new_name="${prefix}_${new_date}_${new_time}_00_${sequence}.${ext}"

    # Check if changes are needed
    if ! needs_changes "$file" "$new_name"; then
      if [[ $verbose -eq 1 ]]; then
        echo "✅ $file (no changes needed)"
      fi
      skipped_count=$((skipped_count + 1))
      continue
    fi

    match_count=$((match_count + 1))

    # Format for display
    orig_display="${orig_date:0:4}-${orig_date:4:2}-${orig_date:6:2} ${orig_time:0:2}:${orig_time:2:2}:${orig_time:4:2}"
    new_display="${new_date:0:4}-${new_date:4:2}-${new_date:6:2} ${new_time:0:2}:${new_time:2:2}:${new_time:4:2}"

    if [[ "$apply_changes" -eq 1 ]]; then
      # Determine destination path
      dest_file=""
      if [[ "$overwrite_in_place" -eq 1 ]]; then
        # Rename in the same directory as the original file
        file_dir="$(dirname "$file")"
        dest_file="$file_dir/$new_name"
        echo "📄 $file → $dest_file"
        mv "$file" "$dest_file"
      else
        # Preserve directory structure in corrected/
        file_dir="$(dirname "$file")"
        dest_dir="corrected/$file_dir"
        mkdir -p "$dest_dir"
        dest_file="$dest_dir/$new_name"
        echo "📄 $file → $dest_file"
        cp "$file" "$dest_file"
      fi
      
      # Update all timestamps using the library functions
      # First read existing timestamps to determine what needs updating
      get_file_timestamps "$dest_file" || true

      local_tz=$(date +%z)
      corrected_with_tz="${new_date:0:4}:${new_date:4:2}:${new_date:6:2} ${new_time:0:2}:${new_time:2:2}:${new_time:4:2}${local_tz}"
      utc_time=$(to_utc "$corrected_with_tz" || echo "")

      if [[ -n "$utc_time" ]]; then
        set_file_timestamps "$dest_file" "$corrected_with_tz" "$utc_time" || true
      fi
      
      # Set file modification time
      touch_timestamp="$(date -j -r "$corrected_epoch" "+%Y%m%d%H%M.%S")"
      touch -t "$touch_timestamp" "$dest_file"
      
      # Set creation date using SetFile if available
      if command -v SetFile >/dev/null 2>&1; then
        SetFile -d "$(date -j -r "$corrected_epoch" "+%m/%d/%Y %H:%M:%S")" "$dest_file"
      fi
    else
      # Dry run - show what would be done
      if [[ "$overwrite_in_place" -eq 1 ]]; then
        file_dir="$(dirname "$file")"
        echo "📄 $file → $file_dir/$new_name (rename)"
      else
        file_dir="$(dirname "$file")"
        echo "📄 $file → corrected/$file_dir/$new_name (copy)"
      fi
    fi
  done < <(find . -name corrected -prune -o -name "*.$ext" -type f -print0)
done

# Summary
echo ""
if [[ $match_count -eq 0 && $skipped_count -eq 0 ]]; then
  echo "⚠️  No matching files found"
elif [[ $match_count -eq 0 ]]; then
  echo "✅ All $skipped_count files already have correct timestamps"
else
  echo "✅ Processed: $match_count files"
  if [[ $skipped_count -gt 0 ]]; then
    echo "ℹ️  Skipped: $skipped_count files (already correct)"
  fi
  
  if [[ "$apply_changes" -eq 0 ]]; then
    echo "🧪 This was a DRY RUN. Use --apply to make changes."
  fi
fi