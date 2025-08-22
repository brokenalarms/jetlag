#!/bin/bash

# Usage:
# ./offset_filename_datetime_v2.sh --base <misdated_file> --correct <YYYYMMDD_HHMMSS> --filter <prefix> [--apply] [--overwrite]
#
# This script corrects Insta360 files that were shot with wrong date/time settings
# It offsets both the filename and file modification time to the correct values

apply_changes=0
overwrite_in_place=0
match_count=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base) base_file="$2"; shift 2 ;;
    --correct) correct_str="$2"; shift 2 ;;
    --filter) filter_prefix="$2"; shift 2 ;;
    --apply) apply_changes=1; shift ;;
    --overwrite) overwrite_in_place=1; shift ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

if [[ -z "$base_file" || -z "$correct_str" || -z "$filter_prefix" ]]; then
  echo "Usage: $0 --base <misdated_file> --correct <YYYYMMDD_HHMMSS> --filter <prefix> [--apply] [--overwrite]"
  echo ""
  echo "  --base:     Reference file with wrong datetime (e.g., VID_20250505_133018_00_042.insv)"
  echo "  --correct:  What the datetime should be for that file (e.g., 20250505_130334)"
  echo "  --filter:   Filter files by date prefix (e.g., 20250505 to only process that day)"
  echo "  --apply:    Actually apply changes (default is dry run)"
  echo "  --overwrite: Rename files in place (default is copy to ./corrected/)"
  exit 1
fi

if ! [[ "$correct_str" =~ ^[0-9]{8}_[0-9]{6}$ ]]; then
  echo "ERROR: --correct must be in format YYYYMMDD_HHMMSS, e.g., 20250505_130334"
  exit 1
fi

if [[ "$overwrite_in_place" -eq 0 ]]; then
  mkdir -p corrected
fi

# Parse base and correct timestamps
base_full=$(echo "$base_file" | grep -oE '[0-9]{8}_[0-9]{6}')
base_date="${base_full%_*}"
base_time="${base_full#*_}"

correct_date="${correct_str%_*}"
correct_time="${correct_str#*_}"

# Calculate offset in seconds
# Parse as local time (not UTC) since these are shooting times
base_epoch=$(date -j -f "%Y%m%d%H%M%S" "${base_date}${base_time}" +%s)
correct_epoch=$(date -j -f "%Y%m%d%H%M%S" "${correct_date}${correct_time}" +%s)
offset_sec=$((correct_epoch - base_epoch))

# Human-readable offset
days_to_add=$((offset_sec / 86400))
hours_to_add=$(( (offset_sec % 86400) / 3600 ))
minutes_to_add=$(( (offset_sec % 3600) / 60 ))
seconds_to_add=$((offset_sec % 60))

# Format offset display with sign
if [[ $offset_sec -ge 0 ]]; then
  offset_sign="+"
else
  offset_sign=""
  days_to_add=$((days_to_add * -1))
  hours_to_add=$((hours_to_add * -1))
  minutes_to_add=$((minutes_to_add * -1))
  seconds_to_add=$((seconds_to_add * -1))
fi

echo "---------------------------------------------------"
echo "Insta360 Filename/Timestamp Correction"
echo "---------------------------------------------------"
echo "Base file:     $base_file"
echo "  Wrong time:  ${base_date:0:4}-${base_date:4:2}-${base_date:6:2} ${base_time:0:2}:${base_time:2:2}:${base_time:4:2}"
echo "Correct time:  ${correct_date:0:4}-${correct_date:4:2}-${correct_date:6:2} ${correct_time:0:2}:${correct_time:2:2}:${correct_time:4:2}"
echo "Offset:        ${offset_sign}${days_to_add}d ${hours_to_add}h ${minutes_to_add}m ${seconds_to_add}s"
echo "Filter prefix: $filter_prefix"
if [[ "$apply_changes" -eq 1 ]]; then
  if [[ "$overwrite_in_place" -eq 1 ]]; then
    echo "Mode:          APPLYING changes (rename in place)"
  else
    echo "Mode:          APPLYING changes (copy to ./corrected)"
  fi
else
  echo "Mode:          DRY RUN (no files will be changed)"
fi
echo "---------------------------------------------------"
echo ""

# Process all matching files
for ext in insv lrv mp4 mov INSV LRV MP4 MOV; do
  for file in *.$ext; do
    # Check if file exists and matches filter
    [[ -f "$file" ]] || continue
    [[ $file == VID_${filter_prefix}* ]] || continue

    match_count=$((match_count + 1))

    # Parse filename components
    IFS='_.' read -r _ orig_date orig_time _ sequence _ <<< "$file"

    if [[ -z "$orig_date" || -z "$orig_time" || -z "$sequence" ]]; then
      echo "❌ Failed to parse: $file"
      continue
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
    new_name="VID_${new_date}_${new_time}_00_${sequence}.${ext}"

    # Format for display
    orig_display="${orig_date:0:4}-${orig_date:4:2}-${orig_date:6:2} ${orig_time:0:2}:${orig_time:2:2}:${orig_time:4:2}"
    new_display="${new_date:0:4}-${new_date:4:2}-${new_date:6:2} ${new_time:0:2}:${new_time:2:2}:${new_time:4:2}"

    echo "📄 $file"
    echo "   Original: $orig_display"
    echo "   Corrected: $new_display"

    if [[ "$apply_changes" -eq 1 ]]; then
      # Create timestamp string for touch command (local time, not UTC)
      touch_timestamp="$(date -j -r "$corrected_epoch" "+%Y%m%d%H%M.%S")"
      
      if [[ "$overwrite_in_place" -eq 1 ]]; then
        echo "   → Renaming to: $new_name"
        mv "$file" "$new_name"
        touch -t "$touch_timestamp" "$new_name"
        
        # Also set creation date using SetFile if available
        if command -v SetFile >/dev/null 2>&1; then
          SetFile -d "$(date -j -r "$corrected_epoch" "+%m/%d/%Y %H:%M:%S")" "$new_name"
        fi
      else
        dest_path="corrected/$new_name"
        echo "   → Copying to: $dest_path"
        cp "$file" "$dest_path"
        touch -t "$touch_timestamp" "$dest_path"
        
        # Also set creation date using SetFile if available
        if command -v SetFile >/dev/null 2>&1; then
          SetFile -d "$(date -j -r "$corrected_epoch" "+%m/%d/%Y %H:%M:%S")" "$dest_path"
        fi
      fi
    else
      if [[ "$overwrite_in_place" -eq 1 ]]; then
        echo "   → Would rename to: $new_name"
      else
        echo "   → Would copy to: corrected/$new_name"
      fi
    fi

    echo ""
  done
done

echo "---------------------------------------------------"
if [[ $match_count -eq 0 ]]; then
  echo "⚠️  No files matched the filter: VID_${filter_prefix}*"
else
  echo "✅ Total files processed: $match_count"
fi

if [[ "$apply_changes" -eq 0 ]]; then
  echo ""
  echo "This was a DRY RUN. Use --apply to make changes."
fi