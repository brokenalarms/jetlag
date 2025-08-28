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

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) apply=1; shift ;;
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
      echo "  --template TMPL     Path template (default: {{YYYY-MM-DD}})"
      echo "                      Variables: {{YYYY}}, {{MM}}, {{DD}}, {{YYYY-MM-DD}}, {{label}}"
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

# Helper functions
log_verbose() {
  [[ $verbose -eq 1 ]] && echo "$@" >&2
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
    template_path="{{YYYY-MM-DD}}"
  fi
  local organized_path
  if ! organized_path="$(expand_path_template "$template_path" "$file_date" "$label")"; then
    return 1
  fi
  
  # Create target path (handle trailing/leading slashes)
  local target_path="${target_dir%/}/${organized_path#/}"
  local target_file="$target_path/$base"
  
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
      echo "✓ Duplicate file exists, removing source: $base → $organized_path/"
      if [[ $apply -eq 1 ]]; then
        rm "$file"
        echo "   ✅ Source removed"
      else
        echo "   [DRY RUN] Would remove source"
      fi
    else
      echo "⚠️  Target file exists with different size: $base → $organized_path/"
      return 1
    fi
  else
    # Move file to target
    echo "📁 Moving: $base → $organized_path/"
    if [[ $apply -eq 1 ]]; then
      mkdir -p "$target_path"
      mv "$file" "$target_file"
      echo "   ✅ Moved"
    else
      echo "   [DRY RUN] Would move to $target_path/"
    fi
  fi
  
  return 0
}

# Process the file
if process_file "$file"; then
  if [[ $apply -eq 1 ]]; then
    echo "✅ File organization complete - changes applied."
  else
    echo "✅ File organization complete - DRY RUN (no changes made)."
  fi
else
  echo "❌ File organization failed."
  exit 1
fi