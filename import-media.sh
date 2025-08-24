#!/usr/bin/env bash
# import-media.sh
# Generic media import script for organizing files from memory cards
# Usage: import-media.sh [DIRNAME] --dest DESTINATION [--apply]
# Copies from DIRNAME/ to DESTINATION/YYYY-MM-DD/
# Then renames DIRNAME to "DIRNAME - copied YYYY-MM-DD"
# DRY-RUN by default; copies only when --apply is present.

set -euo pipefail
IFS=$'\n\t'

# Load environment variables if available
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/.env.local" ]]; then
  source "${SCRIPT_DIR}/.env.local"
elif [[ -f "./.env.local" ]]; then
  source "./.env.local"
fi

# Parse arguments
APPLY=0
DIR=""
DEST=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --apply)
      APPLY=1
      shift
      ;;
    --dest)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --dest requires a destination path" >&2; exit 1; }
      # Expand environment variables in destination
      DEST=$(eval echo "$1")
      shift
      ;;
    --help|-h)
      echo "Usage: $0 [DIRNAME] --dest DESTINATION [--apply]"
      echo ""
      echo "Copies media files from a source directory to a destination organized by date"
      echo ""
      echo "Arguments:"
      echo "  DIRNAME      Source directory (auto-detected if only one subdirectory exists)"
      echo "  --dest PATH  Destination path (can use env variables like '\$DJI_RAW_FOLDER')"
      echo "  --apply      Execute the copy (default is dry-run)"
      echo ""
      echo "Examples:"
      echo "  $0 --dest '\$INSTA360_RAW_FOLDER' --apply"
      echo "  $0 DJI_0001 --dest '\$DJI_RAW_FOLDER' --apply"
      echo "  $0 GoPro --dest '/Volumes/Backup/GoPro/Raw' --apply"
      exit 0
      ;;
    *)
      DIR="$1"
      shift
      ;;
  esac
done

# Check destination is provided
if [[ -z "$DEST" ]]; then
  echo "ERROR: --dest DESTINATION is required" >&2
  echo "Use --help for usage information" >&2
  exit 1
fi

# If no directory specified, look for a single subdirectory
if [[ -z "$DIR" ]]; then
  count=0
  for d in */; do
    [[ -d "$d" ]] || continue
    # Skip already processed directories
    [[ "${d%/}" =~ "- copied" ]] && continue
    DIR="${d%/}"
    count=$((count+1))
  done
  
  if [[ $count -eq 0 ]]; then
    echo "ERROR: No unprocessed subdirectories found in current directory" >&2
    exit 1
  elif [[ $count -gt 1 ]]; then
    echo "ERROR: Multiple subdirectories found. Please specify which one to process:" >&2
    for d in */; do
      [[ -d "$d" ]] || continue
      [[ "${d%/}" =~ "- copied" ]] && continue
      echo "  ${d%/}" >&2
    done
    echo "Usage: $0 DIRNAME --dest DESTINATION [--apply]" >&2
    exit 1
  fi
fi

# Validate directory exists
if [[ ! -d "$DIR" ]]; then
  echo "ERROR: Directory '$DIR' not found" >&2
  exit 1
fi

# Check if directory was already processed
if [[ "$DIR" =~ "- copied" ]]; then
  echo "WARNING: Directory '$DIR' appears to have already been processed (contains '- copied')" >&2
  read -p "Continue anyway? (y/N) " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 0
  fi
fi

echo "→ Source:      $DIR/"
echo "→ Destination: $DEST/"
echo "→ Mode:        $([[ $APPLY -eq 1 ]] && echo APPLY || echo 'DRY RUN (no changes)')"
echo

# Helper: extract YYYY-MM-DD from various filename patterns
derive_date_from_filename() {
  local base="$1"
  
  # Pattern 1: VID_YYYYMMDD_HHMMSS (Insta360)
  if [[ "$base" =~ VID_([0-9]{4})([0-9]{2})([0-9]{2})_ ]]; then
    echo "${BASH_REMATCH[1]}-${BASH_REMATCH[2]}-${BASH_REMATCH[3]}"
    return 0
  fi
  
  # Pattern 2: IMG_YYYYMMDD_HHMMSS (Insta360)
  if [[ "$base" =~ IMG_([0-9]{4})([0-9]{2})([0-9]{2})_ ]]; then
    echo "${BASH_REMATCH[1]}-${BASH_REMATCH[2]}-${BASH_REMATCH[3]}"
    return 0
  fi
  
  # Pattern 3: LRV_YYYYMMDD_HHMMSS (Insta360 Low res video)
  if [[ "$base" =~ LRV_([0-9]{4})([0-9]{2})([0-9]{2})_ ]]; then
    echo "${BASH_REMATCH[1]}-${BASH_REMATCH[2]}-${BASH_REMATCH[3]}"
    return 0
  fi
  
  # Pattern 4: DJI_YYYYMMDDHHMMSS_* (DJI Mavic 3 and newer)
  if [[ "$base" =~ DJI_([0-9]{4})([0-9]{2})([0-9]{2})([0-9]{6})_ ]]; then
    echo "${BASH_REMATCH[1]}-${BASH_REMATCH[2]}-${BASH_REMATCH[3]}"
    return 0
  fi
  
  # Pattern 5: DSC_YYYYMMDD_HHMMSS (Sony cameras)
  if [[ "$base" =~ DSC_([0-9]{4})([0-9]{2})([0-9]{2})_ ]]; then
    echo "${BASH_REMATCH[1]}-${BASH_REMATCH[2]}-${BASH_REMATCH[3]}"
    return 0
  fi
  
  # Pattern 6: GOPR#### or GP###### (GoPro) - no date in filename
  # Pattern 7: DJI_0001 format (older DJI) - no date in filename
  
  # Pattern 8: Generic YYYYMMDD anywhere in filename
  if [[ "$base" =~ ([0-9]{4})([0-9]{2})([0-9]{2}) ]]; then
    local year="${BASH_REMATCH[1]}"
    local month="${BASH_REMATCH[2]}"
    local day="${BASH_REMATCH[3]}"
    # Basic validation: year should be 2000-2099, month 01-12, day 01-31
    if [[ $year -ge 2000 && $year -le 2099 && $month -ge 1 && $month -le 12 && $day -ge 1 && $day -le 31 ]]; then
      echo "${year}-${month}-${day}"
      return 0
    fi
  fi
  
  return 1
}

# Process files
copied=0
skipped=0
planned=0
dates_used=()
current_date=$(date +%Y-%m-%d)
renamed_dir=""

# Count total files first for progress
total_files=$(find "$DIR" -type f ! -name ".*" | wc -l | tr -d ' ')
processed=0

echo "Found $total_files file(s) to process"
echo

# Find all files in the directory
while IFS= read -r file; do
  base="$(basename "$file")"
  processed=$((processed+1))
  
  # Skip system files
  [[ "$base" == ".DS_Store" ]] && continue
  [[ "$base" == "Thumbs.db" ]] && continue
  
  # Try to extract date from filename
  if date_str=$(derive_date_from_filename "$base"); then
    dest_date="$date_str"
    date_source="filename"
  else
    # Fallback to file creation time (birth time)
    if [[ "$(uname)" == "Darwin" ]]; then
      # macOS: Use birth time (creation time)
      dest_date=$(stat -f "%SB" -t "%Y-%m-%d" "$file")
      date_source="created"
    else
      # Linux: Try birth time if available, otherwise use mtime
      if stat --version 2>/dev/null | grep -q GNU; then
        # GNU stat (most Linux)
        birth_time=$(stat -c "%W" "$file" 2>/dev/null)
        if [[ "$birth_time" != "-" && "$birth_time" != "0" ]]; then
          dest_date=$(date -d "@$birth_time" +%Y-%m-%d)
          date_source="created"
        else
          # Fall back to mtime if birth time not available
          dest_date=$(date -r "$file" +%Y-%m-%d)
          date_source="modified"
        fi
      else
        # Other Unix, use mtime
        dest_date=$(date -r "$file" +%Y-%m-%d)
        date_source="modified"
      fi
    fi
  fi
  
  # Track dates for renaming
  if [[ ! " ${dates_used[@]+"${dates_used[@]}"} " =~ " ${dest_date} " ]]; then
    dates_used+=("$dest_date")
  fi
  
  destdir="$DEST/$dest_date"
  destfile="$destdir/$base"
  
  if [[ $APPLY -eq 1 ]]; then
    mkdir -p "$destdir"
    
    if [[ -e "$destfile" ]]; then
      # File exists, check if same size first (faster than full compare)
      src_size=$(stat -f "%z" "$file" 2>/dev/null || stat -c "%s" "$file" 2>/dev/null)
      dst_size=$(stat -f "%z" "$destfile" 2>/dev/null || stat -c "%s" "$destfile" 2>/dev/null)
      
      if [[ "$src_size" == "$dst_size" ]]; then
        echo "[$processed/$total_files] ✓ Same size file exists at destination, skipping: $base"
        skipped=$((skipped+1))
      else
        echo "[$processed/$total_files] ⚠️  Different size file exists, keeping source: $base"
      fi
    else
      echo "[$processed/$total_files] Copying $base → $destdir/ (date from $date_source)"
      cp -p "$file" "$destfile"
      # Verify copy was successful before moving source to renamed folder
      if cmp -s "$file" "$destfile" 2>/dev/null; then
        # Create renamed directory after first successful copy if not exists
        if [[ -z "$renamed_dir" ]]; then
          # Use today's date for the renamed folder
          renamed_dir="${DIR} - copied ${current_date}"
          mkdir -p "$renamed_dir"
          echo "Created archive folder: $renamed_dir"
        fi
        mv "$file" "$renamed_dir/$(basename "$file")"
        copied=$((copied+1))
      else
        echo "  ⚠️  Copy verification failed, keeping source file in place"
      fi
    fi
  else
    echo "[DRY] Would copy $base → $destdir/ (date from $date_source)"
    planned=$((planned+1))
  fi
done < <(find "$DIR" -type f ! -name ".*")

echo

if [[ $APPLY -eq 1 ]]; then
  # Remove original directory if it's empty and we created a renamed one
  if [[ -n "$renamed_dir" ]] && [[ -d "$DIR" ]]; then
    if find "$DIR" -type f ! -name ".*" | head -1 | grep -q .; then
      echo "⚠️  Original folder '$DIR' still contains files (copy may have been interrupted)"
    else
      echo "Removing empty original folder: $DIR"
      rmdir "$DIR" 2>/dev/null || echo "  Note: Folder not empty (may contain hidden files)"
    fi
  fi
  
  if [[ $copied -gt 0 || $skipped -gt 0 ]]; then
    echo
    echo "✅ Summary:"
    [[ $copied -gt 0 ]] && echo "   - Copied: $copied file(s)"
    [[ $skipped -gt 0 ]] && echo "   - Skipped: $skipped file(s) (already exist with same size)"
    [[ -n "$renamed_dir" ]] && echo "   - Archived to: $renamed_dir"
  else
    echo "✅ No new files to copy"
  fi
else
  # Use today's date for showing what would happen
  new_name="${DIR} - copied ${current_date}"
  
  echo "🧪 Dry run complete. Would copy $planned file(s)"
  if [[ $planned -gt 0 ]]; then
    echo "   Would organize into these date folders:"
    printf '%s\n' "${dates_used[@]}" | sort -u | while read -r date; do
      echo "   - $date/"
    done
    echo "   Would create archive: '$new_name'"
    echo "   Would remove original: '$DIR'"
  fi
  echo
  echo "   Re-run with --apply to execute"
fi