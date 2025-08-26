#!/usr/bin/env bash
# organize-videos-by-date.sh
# Fixes video timestamps and organizes them into date-based folders
# Run from folder containing: Exports/  Ready/  (Raw/ optional)
# Usage: organize-videos-by-date.sh --dir DIRNAME [--country COUNTRY | --timezone +HHMM] [--apply]
# Creates folder structure: Ready/YYYY/DIRNAME/YYYY-MM-DD/
# DRY-RUN by default; moves only when --apply is present.

set -euo pipefail
IFS=$'\n\t'

# Get script directory for calling organize-by-date.sh
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source library files
source "$SCRIPT_DIR/lib/lib-file-ops.sh"

ROOT="$PWD"
EXPORTS="$ROOT/Exports"
READY="$ROOT/Ready"

[[ -d "$EXPORTS" ]] || { echo "ERROR: Exports/ not found in $ROOT" >&2; exit 1; }
mkdir -p "$READY"

command -v fix-video-timestamp.sh >/dev/null || {
  echo "fix-video-timestamp.sh not in PATH" >&2; exit 1; }
command -v organize-by-date.sh >/dev/null || {
  echo "organize-by-date.sh not in PATH" >&2; exit 1; }

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

# If no --country was provided but --dir looks like a country, use it
if [[ ! " ${NORMALIZE_ARGS[@]+"${NORMALIZE_ARGS[@]}"} " =~ " --country " ]]; then
  # Try using DIR as country
  NORMALIZE_ARGS+=("--country" "$DIR")
fi

echo "→ Root:    $ROOT"
echo "→ Exports: $EXPORTS"
echo "→ Ready:   $READY"
echo "→ Dir:     $DIR"
echo "→ Mode:    $([[ $APPLY -eq 1 ]] && echo APPLY || echo 'DRY RUN (no changes)')"
echo "→ Processing files with args: ${NORMALIZE_ARGS[*]:-}"
echo

# Count total files for progress tracking
total_files=0
for f in "$EXPORTS"/*.mp4 "$EXPORTS"/*.MP4 "$EXPORTS"/*.mov "$EXPORTS"/*.MOV; do
  [[ -e "$f" ]] && total_files=$((total_files + 1))
done

if [[ $total_files -eq 0 ]]; then
  echo "No video files found in $EXPORTS"
  exit 0
fi

echo "📹 Found $total_files video file(s) to process"
echo

# Process each file individually: fix timestamp → organize file
moved=0
planned=0
processed=0
TMP_SUMMARY="$(mktemp)"

for f in "$EXPORTS"/*.mp4 "$EXPORTS"/*.MP4 "$EXPORTS"/*.mov "$EXPORTS"/*.MOV; do
  [[ -e "$f" ]] || continue
  processed=$((processed + 1))
  base="$(basename "$f")"
  
  echo "[$processed/$total_files] Processing: $base"
  
  # Step 1: Fix timestamp for this file
  ORIG_PWD="$PWD"
  cd "$EXPORTS"
  fix-video-timestamp.sh "$f" ${NORMALIZE_ARGS[@]+"${NORMALIZE_ARGS[@]}"} || {
    echo "⚠️  Timestamp processing failed for $base, skipping..."
    cd "$ORIG_PWD"
    continue
  }
  cd "$ORIG_PWD"
  
  # Step 2: Organize this file using the modular organize script
  # Move to Ready directory first
  ready_dir="$READY/$y/$DIR"
  mkdir -p "$ready_dir"
  
  if [[ $APPLY -eq 1 ]]; then
    # Move file to Ready directory, then organize by date
    if [[ ! -e "$ready_dir/$base" ]]; then
      echo "📄 Moving $base → Ready/$y/$DIR/"
      cp -p "$f" "$ready_dir/$base" && rm "$f"
      
      # Now organize by date within the Ready directory
      organize-by-date.sh --dir "$ready_dir" --apply || {
        echo "⚠️  Organization failed for $base"
      }
      moved=$((moved+1))
    else
      echo "⚠️  Target file already exists, skipping: $ready_dir/$base"
    fi
  else
    # Dry run - show what would happen
    echo "📄 [DRY] Would move $base → Ready/$y/$DIR/"
    echo "📄 [DRY] Would organize by date in Ready/$y/$DIR/"
    # For summary, determine what the final path would be
    if date_str=$(derive_date_from_filename "$base"); then
      final_path="$y/${DIR}/${date_str}"
    else
      final_date=$(date -r "$f" +%Y-%m-%d)
      final_path="$y/${DIR}/${final_date}"
    fi
    printf '%s|%s\n' "$final_path" "$base" >> "$TMP_SUMMARY"
    planned=$((planned+1))
  fi
  
  echo  # Empty line between files
done

if [[ $APPLY -eq 1 ]]; then
  echo "✅ Processing complete: $moved file(s) processed and organized into date folders"
else
  echo "🧪 DRY RUN complete - would process and organize $planned file(s):"
  if (( planned > 0 )); then
    echo
    echo "── Target structure under Ready/$y/$DIR/ ──"
    sort "$TMP_SUMMARY" | cut -d'|' -f1 | uniq -c | while read count key; do
      echo "$key: $count file(s)"
    done
    echo
    echo "Use --apply to execute timestamp fixes and file organization."
  fi
fi

rm -f "$TMP_SUMMARY"
