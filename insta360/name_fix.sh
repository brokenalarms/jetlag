#!/bin/bash

# Usage:
# ./name_fix.sh --timezone +0200 --filter <prefix> [--apply]

apply_changes=0
timezone_offset=""
filter_prefix=""
match_count=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --timezone) timezone_offset="$2"; shift 2 ;;
    --filter) filter_prefix="$2"; shift 2 ;;
    --apply) apply_changes=1; shift ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

if [[ -z "$timezone_offset" || -z "$filter_prefix" ]]; then
  echo "Usage: $0 --timezone <+HHMM/-HHMM> --filter <prefix> [--apply]"
  exit 1
fi

echo "----------------------------------------------------"
echo "Filename UTC Correction for Insta360"
echo "Timezone offset: $timezone_offset"
echo "Filter prefix:   $filter_prefix"
if [[ "$apply_changes" -eq 1 ]]; then
  echo "Mode:            APPLYING changes"
else
  echo "Mode:            DRY RUN (no files will be changed)"
fi
echo "----------------------------------------------------"

for file in VID_"$filter_prefix"*.*; do
  [[ -f "$file" ]] || continue

  ext="${file##*.}"
  name_part="${file%.*}"

  if [[ ! "$name_part" =~ VID_([0-9]{8})_([0-9]{6})_00_([0-9]+) ]]; then
    echo "Skipping: $file (unrecognized format)"
    continue
  fi

  match_count=$((match_count + 1))
  orig_date="${BASH_REMATCH[1]}"
  orig_time="${BASH_REMATCH[2]}"
  sequence="${BASH_REMATCH[3]}"
  datetime_local="${orig_date}${orig_time}"

  # Convert to UTC
  utc_epoch=$(TZ="UTC" date -j -f "%Y%m%d%H%M%S %z" "${datetime_local} ${timezone_offset}" +%s 2>/dev/null)
  if [[ -z "$utc_epoch" ]]; then
    echo "❌ Failed to convert: $file"
    continue
  fi

  utc_date=$(date -u -r "$utc_epoch" "+%Y%m%d")
  utc_time=$(date -u -r "$utc_epoch" "+%H%M%S")
  new_name="VID_${utc_date}_${utc_time}_00_${sequence}.${ext}"

  if [[ "$file" == "$new_name" ]]; then
    echo "✅ $file is already correct"
    continue
  fi

  if [[ "$apply_changes" -eq 1 ]]; then
    mv "$file" "$new_name"
    echo "✅ Renamed to: $new_name"
  else
    echo "DRY RUN: Would rename $file -> $new_name"
  fi
done

echo "✅ Total matched: $match_count"
