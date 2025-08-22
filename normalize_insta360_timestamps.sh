#!/bin/bash
# normalize_video_timestamps.sh
# Requires: exiftool, SetFile, python3
# Usage: ./normalize_video_timestamps.sh [--apply] [--timezone +0900]
# Scans the current directory tree for *.mp4/*.mov

set -euo pipefail
IFS=$'\n\t'

apply=0
cli_tz=""

# ---------- args ----------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) apply=1; shift ;;
    --timezone)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --timezone needs +HHMM or +HH:MM"; exit 1; }
      cli_tz="$1"; shift ;;
    *) shift ;;
  esac
done

# ---------- helpers ----------
fix_colon_tz() {
  echo "$1" | sed -E 's/([+-][0-9]{2}):?([0-9]{2})$/\1\2/'
}

to_utc() {
  python3 - "$1" <<'PY'
import sys
from datetime import datetime, timezone
s = sys.argv[1]
dt = datetime.strptime(s, '%Y:%m:%d %H:%M:%S%z')
print(dt.astimezone(timezone.utc).strftime('%Y:%m:%d %H:%M:%S'))
PY
}

# A) TIMEZONE picking (CLI → timezone.txt → DateTimeOriginal)
get_timezone() {
  local file="$1" dir tz dto
  dir="$(dirname "$file")"

  if [[ -n "$cli_tz" ]]; then
    echo "$(fix_colon_tz "$cli_tz")"
    return 0
  fi

  if [[ -f "$dir/timezone.txt" ]]; then
    tz="$(head -n1 "$dir/timezone.txt")"
    chflags hidden "$dir/timezone.txt" 2>/dev/null || true
    echo "$(fix_colon_tz "$tz")"
    return 0
  fi

  dto="$(exiftool -s3 -DateTimeOriginal "$file" 2>/dev/null || true)"
  if [[ "$dto" =~ [+-][0-9]{2}(:?[0-9]{2})$ ]]; then
    echo "$(fix_colon_tz "${dto:19}")"
    return 0
  fi

  return 1
}

# B) DATETIME picking (filename → DateTimeOriginal → MediaCreateDate → mtime)
get_datetime_local() {
  local file="$1" base dto mcd
  base="$(basename "$file")"

  if [[ "$base" =~ ^VID_([0-9]{8})_([0-9]{6}) ]]; then
    local d="${BASH_REMATCH[1]}" t="${BASH_REMATCH[2]}"
    echo "${d:0:4}:${d:4:2}:${d:6:2} ${t:0:2}:${t:2:2}:${t:4:2}"
    return 0
  fi

  dto="$(exiftool -s3 -DateTimeOriginal "$file" 2>/dev/null || true)"
  if [[ "$dto" =~ ^([0-9]{4}):([0-9]{2}):([0-9]{2})[[:space:]]([0-9]{2}):([0-9]{2}):([0-9]{2}) ]]; then
    echo "${BASH_REMATCH[1]}:${BASH_REMATCH[2]}:${BASH_REMATCH[3]} ${BASH_REMATCH[4]}:${BASH_REMATCH[5]}:${BASH_REMATCH[6]}"
    return 0
  fi

  mcd="$(exiftool -s3 -QuickTime:MediaCreateDate "$file" 2>/dev/null || true)"
  if [[ "$mcd" =~ ^([0-9]{4}):([0-9]{2}):([0-9]{2})[[:space:]]([0-9]{2}):([0-9]{2}):([0-9]{2}) ]]; then
    echo "${BASH_REMATCH[1]}:${BASH_REMATCH[2]}:${BASH_REMATCH[3]} ${BASH_REMATCH[4]}:${BASH_REMATCH[5]}:${BASH_REMATCH[6]}"
    return 0
  fi

  date -r "$file" +%Y:%m:%d\ %H:%M:%S
}

update_metadata() {
  local file="$1" local_time="$2" utc_time="$3"
  exiftool -overwrite_original \
    "-DateTimeOriginal=$local_time" \
    "-QuickTime:CreateDate=$utc_time" \
    "-QuickTime:ModifyDate=$utc_time" \
    "-FileModifyDate=$utc_time" "$file" >/dev/null 2>&1
  SetFile -d "$(date -j -f "%Y:%m:%d %H:%M:%S" "${local_time:0:19}" "+%m/%d/%Y %H:%M:%S")" "$file"
}

# ---------- main ----------
echo "🕓 Scanning video files..."

find . -type f \( -iname '*.mp4' -o -iname '*.mov' \) -print0 | while IFS= read -r -d '' file; do
  if ! tz="$(get_timezone "$file")"; then
    echo "❌ $file: No timezone (use --timezone or timezone.txt). Aborting." >&2
    exit 1
  fi

  local_dt="$(get_datetime_local "$file")"
  local_with_tz="${local_dt}${tz}"
  utc_time="$(to_utc "$local_with_tz")"

  printf "\033[36m🔍 %s\033[0m\n" "$(basename "$file")"
  printf "⏱️ Local : %s\n" "$local_with_tz"
  printf "🌐 UTC   : %s UTC\n\n" "$utc_time"

  [[ $apply -eq 1 ]] && update_metadata "$file" "$local_with_tz" "$utc_time"
done

echo "✅ Timestamp normalization complete."
