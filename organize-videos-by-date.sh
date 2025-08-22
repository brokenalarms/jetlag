#!/usr/bin/env bash
# organize-videos-by-date.sh
# Fixes video timestamps and organizes them into date-based folders
# Run from folder containing: Exports/  Ready/  (Raw/ optional)
# Usage: organize-videos-by-date.sh --dir DIRNAME [--country COUNTRY | --timezone +HHMM] [--apply]
# Creates folder structure: Ready/YYYY/DIRNAME/YYYY-MM-DD/
# DRY-RUN by default; moves only when --apply is present.

set -euo pipefail
IFS=$'\n\t'

ROOT="$PWD"
EXPORTS="$ROOT/Exports"
READY="$ROOT/Ready"

[[ -d "$EXPORTS" ]] || { echo "ERROR: Exports/ not found in $ROOT" >&2; exit 1; }
mkdir -p "$READY"

command -v fix-video-timestamps.sh >/dev/null || {
  echo "fix-video-timestamps.sh not in PATH" >&2; exit 1; }

# Parse arguments
APPLY=0
DIR=""
NORMALIZE_ARGS=()

while [[ $# -gt 0 ]]; do
  case $1 in
    --apply)
      APPLY=1
      NORMALIZE_ARGS+=("$1")
      shift
      ;;
    --dir)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --dir requires a directory name" >&2; exit 1; }
      DIR="$1"
      shift
      ;;
    *)
      # Pass all other arguments to normalize script
      NORMALIZE_ARGS+=("$1")
      shift
      ;;
  esac
done

# Validate required arguments
[[ -n "$DIR" ]] || { echo "ERROR: --dir DIRNAME is required" >&2; exit 1; }

echo "→ Root:    $ROOT"
echo "→ Exports: $EXPORTS"
echo "→ Ready:   $READY"
echo "→ Dir:     $DIR"
echo "→ Mode:    $([[ $APPLY -eq 1 ]] && echo APPLY || echo 'DRY RUN (no changes)')"
echo "→ Running normalizer with args: ${NORMALIZE_ARGS[*]}"
ORIG_PWD="$PWD"
cd "$EXPORTS"
fix-video-timestamps.sh "${NORMALIZE_ARGS[@]}" || {
  echo "⚠️  Normalizer completed with warnings/errors, continuing with file moves..."
}
cd "$ORIG_PWD"

# --- helper: extract YYYY MM DD from filename (VID_YYYYMMDD pattern) ---
derive_date_from_filename() {
  local base="$1"
  if [[ "$base" =~ VID_([0-9]{4})([0-9]{2})([0-9]{2}) ]]; then
    echo "${BASH_REMATCH[1]}"
    echo "${BASH_REMATCH[2]}"
    echo "${BASH_REMATCH[3]}"
    return 0
  fi
  return 1
}

# --- move or plan using simple globs (Bash 3.2 safe) ---
moved=0
planned=0
TMP_SUMMARY="$(mktemp)"

# Use globs instead of find/pipes
for f in "$EXPORTS"/*.mp4 "$EXPORTS"/*.MP4 "$EXPORTS"/*.mov "$EXPORTS"/*.MOV; do
  [[ -e "$f" ]] || continue
  base="$(basename "$f")"

  if derive_date_from_filename "$base" >/dev/null; then
    {
      read -r y
      read -r m
      read -r d
    } < <(derive_date_from_filename "$base")
  else
    # fallback: file mtime (rare)
    y=$(date -r "$f" +%Y); m=$(date -r "$f" +%m); d=$(date -r "$f" +%d)
  fi

  destdir="$READY/$y/${DIR}/$y-$m-$d"

  if [[ $APPLY -eq 1 ]]; then
    mkdir -p "$destdir"
    echo "Moving $base → $destdir/"
    # Use cp -p to preserve timestamps, then remove original (only if target doesn't exist)
    if [[ ! -e "$destdir/$base" ]]; then
      cp -p "$f" "$destdir/$base" && rm "$f"
    else
      echo "⚠️  Target file already exists, skipping: $destdir/$base"
    fi
    moved=$((moved+1))
  else
    echo "[DRY] Would move $base → $destdir/"
    printf '%s|%s\n' "$y/${DIR}/$y-$m-$d" "$base" >> "$TMP_SUMMARY"
    planned=$((planned+1))
  fi
done

if [[ $APPLY -eq 1 ]]; then
  echo "✅ Moved $moved file(s) into Ready/YYYY/MM/DD"
else
  echo "🧪 Dry run complete. Planned $planned file(s). Re-run with --apply to execute."
  if (( planned > 0 )); then
    echo
    echo "── Dry-run summary (grouped by date) ──"
    sort "$TMP_SUMMARY" | cut -d'|' -f1 | uniq -c | while read count key; do
      echo "$key: $count file(s)"
    done
  fi
fi

rm -f "$TMP_SUMMARY"
