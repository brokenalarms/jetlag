#!/usr/bin/env bash
# organize-by-date.sh
# Organizes a single file into date-based directory structure
# Usage: organize-by-date.sh FILE --target TARGET_DIR [--apply]
# Uses filename date patterns first, falls back to file timestamps

set -euo pipefail
IFS=$'\n\t'

# Get script directory and source libraries
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/lib-timestamp.sh"

# Initialize variables
apply=0
verbose=0
file=""
target_dir=""
template=""
location=""
label=""
copy_mode=0

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) apply=1; shift ;;
    --copy) copy_mode=1; shift ;;
    --verbose|-v) verbose=1; shift ;;
    --target)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --target requires a directory path"; exit 1; }
      target_dir="$1"; shift ;;
    --template)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --template requires a template string"; exit 1; }
      template="$1"; shift ;;
    --location)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --location requires a location name"; exit 1; }
      location="$1"; shift ;;
    --label)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --label requires a label value"; exit 1; }
      label="$1"; shift ;;
    --help|-h)
      echo "Usage: organize-by-date.sh FILE --target TARGET_DIR [OPTIONS]"
      echo "Options:"
      echo "  --target DIR    Target directory for organized files"
      echo "  --copy          Copy file instead of moving (for import operations)"
      echo "  --template TMPL     Path template (default: {{YYYY}}/{{YYY}}-{{MM}}-{{DD}})"
      echo "                      Variables: {{YYYY}}, {{MM}}, {{DD}}, {{label}}"
      echo "  --label LABEL       Label value for {{label}} template variable"
      echo "  --location LOC      Location name for {{location}} template variable (deprecated)"
      echo "  --apply            Apply changes (default: dry run)"
      echo "  --verbose, -v      Show detailed processing info"
      echo "  --help, -h         Show this help"
      exit 0 ;;
    -*) echo "ERROR: Unknown option $1" >&2; exit 1 ;;
    *)
      [[ -z "$file" ]] || { echo "ERROR: Only one file allowed" >&2; exit 1; }
      file="$1"; shift ;;
  esac
done

# Validate arguments
[[ -n "$file" ]] || { echo "ERROR: FILE is required" >&2; exit 1; }
[[ -f "$file" ]] || { echo "ERROR: File not found: $file" >&2; exit 1; }
[[ -n "$target_dir" ]] || { echo "ERROR: --target is required" >&2; exit 1; }

# Expand tilde in target directory
target_dir="${target_dir/#\~/$HOME}"

# Helper functions
log_verbose() {
  [[ $verbose -eq 1 ]] && echo "$@" >&2
}

cleanup_empty_parent_dirs() {
  # Clean up empty parent directories after moving a file
  # Only cleans directories that become empty as a result of this move
  local file_dir="$1"

  # Keep removing parent directories as long as they're empty
  # Stop at root or when we hit a non-empty directory
  while [[ -d "$file_dir" && "$file_dir" != "/" && "$file_dir" != "." ]]; do
    # Try to remove the directory (only succeeds if empty)
    if rmdir "$file_dir" 2>/dev/null; then
      log_verbose "  Removed empty directory: $file_dir"
      # Move up to parent
      file_dir="$(dirname "$file_dir")"
    else
      # Directory not empty or can't be removed, stop here
      break
    fi
  done
}


# Main processing
process_file() {
  local file="$1"
  local base="$(basename "$file")"
  
  log_verbose "Processing: $file"
  
  # Get date for organization
  local file_date
  if ! file_date="$(get_file_date_for_organization "$file")"; then
    echo "ERROR: Cannot determine date for $base" >&2
    return 1
  fi
  
  log_verbose "  Date: $file_date"
  
  # Apply template to create organized path
  local template_path
  if [[ -n "$template" ]]; then
    template_path="$template"
  else
    template_path="{{YYYY}}/{{YYYY}}-{{MM}}-{{DD}}"
  fi
  local organized_path
  if ! organized_path="$(expand_path_template "$template_path" "$file_date" "$label")"; then
    return 1
  fi
  
  # Create target path (handle trailing/leading slashes)
  local target_path="${target_dir%/}/${organized_path#/}"
  local target_file="$target_path/$base"
  
  # Debug: check for newlines
  if [[ "$target_file" =~ $'\n' ]]; then
    echo "DEBUG: target_file contains newline: [$target_file]" >&2
    echo "DEBUG: target_dir=[$target_dir] organized_path=[$organized_path] base=[$base]" >&2
  fi
  
  # Check if file is already in correct location
  if [[ "$(dirname "$(realpath "$file")")" == "$(realpath "$target_path" 2>/dev/null || echo "$target_path")" ]]; then
    echo "✓ Already organized: $base ($organized_path)"
    return 0
  fi
  
  # Check if target file already exists
  if [[ -f "$target_file" ]]; then
    # Compare file sizes
    local src_size dst_size
    src_size=$(stat -f "%z" "$file" 2>/dev/null || stat -c "%s" "$file" 2>/dev/null)
    dst_size=$(stat -f "%z" "$target_file" 2>/dev/null || stat -c "%s" "$target_file" 2>/dev/null)
    
    if [[ "$src_size" -eq "$dst_size" ]]; then
      if [[ $copy_mode -eq 1 ]]; then
        echo "✓ Skipped (already exists): $base → $organized_path/"
        return 0
      else
        if [[ $apply -eq 1 ]]; then
          # Save the source directory before removing
          local source_dir="$(dirname "$file")"
          rm "$file"
          echo "✅ Removed duplicate source: $base (exists at $organized_path/)"

          # Clean up empty parent directories after removing duplicate
          cleanup_empty_parent_dirs "$source_dir"
        else
          echo "[DRY RUN] Would remove duplicate: $file (already at $target_file)"
        fi
      fi
    elif [[ "$dst_size" -lt "$src_size" ]]; then
      if [[ $apply -eq 1 ]]; then
        mkdir -p "$target_path" || return 1
        if [[ $copy_mode -eq 1 ]]; then
          cp -p "$file" "$target_file" || return 1
          echo "✅ Copied (replaced smaller): $base → $organized_path/"
        else
          # Save the source directory before moving
          local source_dir="$(dirname "$file")"
          mv "$file" "$target_file" || return 1
          echo "✅ Moved (replaced smaller): $base → $organized_path/"

          # Clean up empty parent directories after moving
          cleanup_empty_parent_dirs "$source_dir"
        fi
      else
        echo "[DRY RUN] Would overwrite smaller: $file → $target_file"
      fi
    else
      echo "⚠️  Destination larger than source, keeping destination: $base → $organized_path/"
      return 1
    fi
  else
    # Show relative path for input, absolute path for output
    local display_source abs_target
    display_source="$file"  # Keep as-is (relative if user provided relative)
    # Construct absolute target path
    if [[ "$target_file" = /* ]]; then
      abs_target="$target_file"  # Already absolute
    else
      abs_target="$(pwd)/${target_file#./}"  # Make relative path absolute, strip leading ./
    fi

    # Copy or move file to target
    if [[ $apply -eq 1 ]]; then
      mkdir -p "$target_path" || return 1
      if [[ $copy_mode -eq 1 ]]; then
        cp -p "$file" "$target_file" || return 1
        printf "✅ Copied: %s → %s\n" "$display_source" "$abs_target"
      else
        # Save the source directory before moving
        local source_dir="$(dirname "$file")"
        mv "$file" "$target_file" || return 1
        printf "✅ Moved: %s → %s\n" "$display_source" "$abs_target"

        # Clean up empty parent directories after moving
        cleanup_empty_parent_dirs "$source_dir"
      fi
    else
      if [[ $copy_mode -eq 1 ]]; then
        printf "[DRY RUN] Would copy: %s → %s\n" "$display_source" "$abs_target"
      else
        printf "[DRY RUN] Would move: %s → %s\n" "$display_source" "$abs_target"
      fi
    fi
  fi
  
  return 0
}

# Process the file
if ! process_file "$file"; then
  echo "❌ Processing failed."
  exit 1
fi