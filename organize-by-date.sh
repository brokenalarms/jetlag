#!/usr/bin/env bash
# organize-by-date.sh
# Organizes files in current directory into YYYY-MM-DD subdirectories
# Usage: organize-by-date.sh [--apply] [--dir PATH]
# Uses filename date patterns first, falls back to creation time
# DRY-RUN by default; moves files only when --apply is present.

set -euo pipefail
IFS=$'\n\t'

# Get script directory and source libraries
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/lib-common.sh"
source "$SCRIPT_DIR/lib/lib-output.sh"
source "$SCRIPT_DIR/lib/lib-file-ops.sh"

# Parse arguments
TARGET_DIR="."

# Parse common arguments first
remaining_args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)
      shift
      [[ $# -gt 0 ]] || { print_error "--dir requires a directory path"; exit 1; }
      TARGET_DIR="$1"
      shift
      ;;
    --help|-h)
      show_standard_help "$0" "Organizes files into YYYY-MM-DD subdirectories based on date" "  --dir PATH   Directory to organize (default: current directory)

Date extraction:
  1. From filename patterns (VID_, IMG_, DJI_, etc.)
  2. Fallback to file creation time"
      exit 0
      ;;
    *)
      remaining_args+=("$1")
      shift
      ;;
  esac
done

# Parse common args (--apply, --verbose)
if ! parse_common_args "${remaining_args[@]}"; then
  print_error "Unknown option: ${remaining_args[*]}"
  exit 1
fi

# Validate directory exists
if [[ ! -d "$TARGET_DIR" ]]; then
  echo "ERROR: Directory '$TARGET_DIR' not found" >&2
  exit 1
fi

print_info "Directory: $TARGET_DIR"
print_mode_status $APPLY
echo

# Functions are now imported from lib-file-ops.sh:
# - derive_date_from_filename()
# - extract_metadata_date()
# - get_file_date()

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
  
  # Get date for file using the library function
  dest_date=$(get_file_date "$file")
  
  # Determine source for display
  if date_str=$(derive_date_from_filename "$base"); then
    date_source="filename"
  elif date_str=$(extract_metadata_date "$file"); then
    date_source="metadata"
  else
    date_source="created"
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
      
      if compare_file_sizes "$file" "$destfile"; then
        print_progress $processed $total_files "✓ Same file exists in $dest_date/, removing duplicate"
        rm "$file"
        skipped=$((skipped+1))
      else
        print_progress $processed $total_files "⚠️  Different file exists with same name in $dest_date/, skipping: $base"
        skipped=$((skipped+1))
      fi
    else
      print_progress $processed $total_files "Moving $base → $dest_date/ (date from $date_source)"
      mv "$file" "$destfile"
      moved=$((moved+1))
    fi
  else
    if [[ -e "$destfile" ]]; then
      src_size=$(stat -f "%z" "$file" 2>/dev/null || stat -c "%s" "$file" 2>/dev/null)
      dst_size=$(stat -f "%z" "$destfile" 2>/dev/null || stat -c "%s" "$destfile" 2>/dev/null)
      
      if compare_file_sizes "$file" "$destfile"; then
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
  print_success "Dry run complete."
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