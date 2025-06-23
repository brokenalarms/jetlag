#!/bin/bash

# Usage:
# ./name_fix.sh --base <misdated_file> --correct <YYYYMMDD_HHMMSS> --filter <prefix> [--apply]

apply_changes=0
match_count=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base) base_file="$2"; shift 2 ;;
    --correct) correct_str="$2"; shift 2 ;;
    --filter) filter_prefix="$2"; shift 2 ;;
    --apply) apply_changes=1; shift ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

if [[ -z "$base_file" || -z "$correct_str" || -z "$filter_prefix" ]]; then
  echo "Usage: $0 --base <misdated_file> --correct <YYYYMMDD_HHMMSS> --filter <prefix> [--apply]"
  exit 1
fi

# Create output directory
mkdir -p corrected

# Parse base and correct timestamps
base_full=$(echo "$base_file" | grep -oE '[0-9]{8}_[0-9]{6}')
base_date="${base_full%_*}"
base_time="${base_full#*_}"

correct_date="${correct_str%_*}"
correct_time="${correct_str#*_}"

base_epoch=$(TZ=UTC date -j -f "%Y%m%d%H%M%S" "${base_date}${base_time}" +%s)
correct_epoch=$(TZ=UTC date -j -f "%Y%m%d%H%M%S" "${correct_date}${correct_time}" +%s)
offset_sec=$((correct_epoch - base_epoch))

days_to_add=$((offset_sec / 86400))
hours_to_add=$(( (offset_sec % 86400) / 3600 ))
minutes_to_add=$(( (offset_sec % 3600) / 60 ))
seconds_to_add=$((offset_sec % 60))

echo "---------------------------------------------------"
echo "Correction preview for Insta360 .insv/.lrv filename/time"
echo "Base file:     $base_file"
echo "Correct time:  $correct_str"
echo "Filter prefix: $filter_prefix"
echo "Mode:          $([[ "$apply_changes" -eq 1 ]] && echo APPLYING changes || echo DRY RUN (no files will be changed))"
echo "Offset:        $days_to_add d, $hours_to_add h, $minutes_to_add m, $seconds_to_add s"
echo "---------------------------------------------------"

for ext in insv lrv; do
  for file in *.$ext; do
    [[ $file == VID_${filter_prefix}* ]] || continue

    echo "Checking: $file"
    match_count=$((match_count + 1))

    IFS='_.' read -r _ orig_date orig_time _ sequence _ <<< "$file"

    if [[ -z "$orig_date" || -z "$orig_time" || -z "$sequence" ]]; then
      echo "Failed to parse filename: $file"
      continue
    fi

    timestamp_input="${orig_date}${orig_time}"
    epoch=$(TZ=UTC date -j -f "%Y%m%d%H%M%S" "$timestamp_input" +%s) || {
      echo "Date parse failed for $file"
      continue
    }

    corrected_epoch=$((epoch + offset_sec))
    new_date=$(TZ=UTC date -j -r "$corrected_epoch" "+%Y%m%d")
    new_time=$(TZ=UTC date -j -r "$corrected_epoch" "+%H%M%S")
    new_name="VID_${new_date}_${new_time}_00_${sequence}.${ext}"
    dest_path="corrected/$new_name"

    if [[ "$apply_changes" -eq 1 ]]; then
      echo "Copying to: $dest_path"
      cp "$file" "$dest_path"
      touch -t "$(TZ=UTC date -j -r "$corrected_epoch" "+%Y%m%d%H%M.%S")" "$dest_path"
    else
      echo "Would copy to: $dest_path"
    fi

    echo "---"
  done
done

echo "✅ Total files matched and processed: $match_count"
