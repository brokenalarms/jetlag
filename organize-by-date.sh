#!/usr/bin/env bash
# organize-by-date.sh
# Organizes files in current directory into YYYY-MM-DD subdirectories
# Usage: organize-by-date.sh [--apply] [--dir PATH]
# Uses filename date patterns first, falls back to creation time
# DRY-RUN by default; moves files only when --apply is present.

set -euo pipefail
IFS=$'\n\t'

# Parse arguments
APPLY=0
TARGET_DIR="."

while [[ $# -gt 0 ]]; do
  case $1 in
    --apply)
      APPLY=1
      shift
      ;;
    --dir)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --dir requires a directory path" >&2; exit 1; }
      TARGET_DIR="$1"
      shift
      ;;
    --help|-h)
      echo "Usage: $0 [--apply] [--dir PATH]"
      echo ""
      echo "Organizes files into YYYY-MM-DD subdirectories based on date"
      echo ""
      echo "Options:"
      echo "  --dir PATH   Directory to organize (default: current directory)"
      echo "  --apply      Execute the organization (default is dry-run)"
      echo "  --help, -h   Show this help message"
      echo ""
      echo "Date extraction:"
      echo "  1. From filename patterns (VID_, IMG_, DJI_, etc.)"
      echo "  2. Fallback to file creation time"
      exit 0
      ;;
    *)
      echo "ERROR: Unknown option $1" >&2
      echo "Use --help for usage information" >&2
      exit 1
      ;;
  esac
done

# Validate directory exists
if [[ ! -d "$TARGET_DIR" ]]; then
  echo "ERROR: Directory '$TARGET_DIR' not found" >&2
  exit 1
fi

echo "→ Directory: $TARGET_DIR"
echo "→ Mode:      $([[ $APPLY -eq 1 ]] && echo APPLY || echo 'DRY RUN (no changes)')"
echo

# Helper: extract YYYY-MM-DD from various filename patterns
derive_date_from_filename() {
  local base="$1"
  
  # Pattern 1: VID_YYYYMMDD_HHMMSS (Insta360)
  if [[ "$base" =~ VID_([0-9]{4})([0-9]{2})([0-9]{2})_ ]]; then
    echo "${BASH_REMATCH[1]}-${BASH_REMATCH[2]}-${BASH_REMATCH[3]}"
    return 0
  fi
  
  # Pattern 2: IMG_YYYYMMDD_HHMMSS (Insta360/phones)
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
  
  # Pattern 6: Screenshot YYYY-MM-DD at HH.MM.SS (macOS screenshots)
  if [[ "$base" =~ Screenshot[[:space:]]([0-9]{4})-([0-9]{2})-([0-9]{2})[[:space:]]at ]]; then
    echo "${BASH_REMATCH[1]}-${BASH_REMATCH[2]}-${BASH_REMATCH[3]}"
    return 0
  fi
  
  # Pattern 7: Photo YYYY-MM-DD (various formats)
  if [[ "$base" =~ Photo[[:space:]]([0-9]{4})-([0-9]{2})-([0-9]{2}) ]]; then
    echo "${BASH_REMATCH[1]}-${BASH_REMATCH[2]}-${BASH_REMATCH[3]}"
    return 0
  fi
  
  # Pattern 8: YYYY-MM-DD in filename
  if [[ "$base" =~ ([0-9]{4})-([0-9]{2})-([0-9]{2}) ]]; then
    local year="${BASH_REMATCH[1]}"
    local month="${BASH_REMATCH[2]}"
    local day="${BASH_REMATCH[3]}"
    # Basic validation
    if [[ $year -ge 2000 && $year -le 2099 && $month -ge 1 && $month -le 12 && $day -ge 1 && $day -le 31 ]]; then
      echo "${year}-${month}-${day}"
      return 0
    fi
  fi
  
  # Pattern 9: Generic YYYYMMDD anywhere in filename
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
moved=0
skipped=0
planned=0
dates_used=()

# Count total files first for progress
total_files=$(find "$TARGET_DIR" -maxdepth 1 -type f ! -name ".*" | wc -l | tr -d ' ')
processed=0

if [[ $total_files -eq 0 ]]; then
  echo "No files to organize in $TARGET_DIR"
  exit 0
fi

echo "Found $total_files file(s) to organize"
echo

# Process each file in the target directory
while IFS= read -r file; do
  base="$(basename "$file")"
  processed=$((processed+1))
  
  # Skip system files
  [[ "$base" == ".DS_Store" ]] && continue
  [[ "$base" == "Thumbs.db" ]] && continue
  [[ "$base" == "desktop.ini" ]] && continue
  
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
  
  # Track dates for summary
  if [[ ! " ${dates_used[@]+"${dates_used[@]}"} " =~ " ${dest_date} " ]]; then
    dates_used+=("$dest_date")
  fi
  
  destdir="$TARGET_DIR/$dest_date"
  destfile="$destdir/$base"
  
  # Check if file is already in correct location
  if [[ "$(dirname "$file")" == "$destdir" ]]; then
    echo "[$processed/$total_files] ✓ Already organized: $base"
    skipped=$((skipped+1))
    continue
  fi
  
  if [[ $APPLY -eq 1 ]]; then
    mkdir -p "$destdir"
    
    if [[ -e "$destfile" ]]; then
      # File exists at destination
      src_size=$(stat -f "%z" "$file" 2>/dev/null || stat -c "%s" "$file" 2>/dev/null)
      dst_size=$(stat -f "%z" "$destfile" 2>/dev/null || stat -c "%s" "$destfile" 2>/dev/null)
      
      if [[ "$src_size" == "$dst_size" ]]; then
        echo "[$processed/$total_files] ✓ Same file exists in $dest_date/, removing duplicate"
        rm "$file"
        skipped=$((skipped+1))
      else
        echo "[$processed/$total_files] ⚠️  Different file exists with same name in $dest_date/, skipping: $base"
        skipped=$((skipped+1))
      fi
    else
      echo "[$processed/$total_files] Moving $base → $dest_date/ (date from $date_source)"
      mv "$file" "$destfile"
      moved=$((moved+1))
    fi
  else
    if [[ -e "$destfile" ]]; then
      src_size=$(stat -f "%z" "$file" 2>/dev/null || stat -c "%s" "$file" 2>/dev/null)
      dst_size=$(stat -f "%z" "$destfile" 2>/dev/null || stat -c "%s" "$destfile" 2>/dev/null)
      
      if [[ "$src_size" == "$dst_size" ]]; then
        echo "[DRY] Would remove duplicate: $base (same file exists in $dest_date/)"
      else
        echo "[DRY] Would skip: $base (different file exists in $dest_date/)"
      fi
      skipped=$((skipped+1))
    else
      echo "[DRY] Would move $base → $dest_date/ (date from $date_source)"
      planned=$((planned+1))
    fi
  fi
done < <(find "$TARGET_DIR" -maxdepth 1 -type f ! -name ".*")

echo

if [[ $APPLY -eq 1 ]]; then
  echo "✅ Organization complete:"
  [[ $moved -gt 0 ]] && echo "   - Moved: $moved file(s) into date folders"
  [[ $skipped -gt 0 ]] && echo "   - Skipped: $skipped file(s)"
  
  if [[ ${#dates_used[@]} -gt 0 ]]; then
    echo "   - Created/used folders:"
    printf '%s\n' "${dates_used[@]}" | sort -u | while read -r date; do
      count=$(find "$TARGET_DIR/$date" -maxdepth 1 -type f ! -name ".*" | wc -l | tr -d ' ')
      echo "     • $date/ ($count files)"
    done
  fi
else
  echo "🧪 Dry run complete."
  [[ $planned -gt 0 ]] && echo "   Would move $planned file(s)"
  [[ $skipped -gt 0 ]] && echo "   Would skip $skipped file(s)"
  
  if [[ $planned -gt 0 && ${#dates_used[@]} -gt 0 ]]; then
    echo "   Would organize into these date folders:"
    printf '%s\n' "${dates_used[@]}" | sort -u | while read -r date; do
      echo "     • $date/"
    done
  fi
  echo
  echo "   Re-run with --apply to execute"
fi