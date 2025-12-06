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
copy_mode=0
overwrite=0

# Result variables
result_dest=""
result_action=""  # copied, moved, skipped, overwrote

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) apply=1; shift ;;
    --copy) copy_mode=1; shift ;;
    --overwrite) overwrite=1; shift ;;
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
    --help|-h)
      echo "Usage: organize-by-date.sh FILE --target TARGET_DIR [OPTIONS]"
      echo "Options:"
      echo "  --target DIR        Target directory for organized files"
      echo "  --copy              Copy file instead of moving (for import operations)"
      echo "  --template TMPL     Path template (default: {{YYYY}}/{{YYYY}}-{{MM}}-{{DD}})"
      echo "                      Variables: {{YYYY}}, {{MM}}, {{DD}}"
      echo "  --overwrite         Overwrite existing files (default: skip)"
      echo "  --apply             Apply changes (default: dry run)"
      echo "  --verbose, -v       Show detailed processing info"
      echo "  --help, -h          Show this help"
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
  if ! organized_path="$(expand_path_template "$template_path" "$file_date")"; then
    echo "ERROR: Failed to expand template for $base" >&2
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
    echo "✓ Already organized: $base ($organized_path)" >&2
    result_dest="$target_file"
    result_action="skipped"
    return 0
  fi

  # Check if target file already exists
  if [[ -f "$target_file" ]]; then
    local src_size dst_size action
    src_size=$(stat -f "%z" "$file" 2>/dev/null || stat -c "%s" "$file" 2>/dev/null)
    dst_size=$(stat -f "%z" "$target_file" 2>/dev/null || stat -c "%s" "$target_file" 2>/dev/null)

    if [[ $overwrite -eq 1 ]]; then
      action="overwrite"
    elif [[ "$src_size" -eq "$dst_size" ]]; then
      # Same size = same file, auto-skip
      action="skip"
    elif [[ $apply -eq 1 ]]; then
      # Prompt user
      echo "⚠️  File exists: $base" >&2
      echo "   Source: $src_size bytes, Dest: $dst_size bytes" >&2
      read -p "   (o)verwrite / (s)kip? " -n 1 -r choice </dev/tty >&2
      echo >&2
      case "$choice" in
        o|O) action="overwrite" ;;
        *) action="skip" ;;
      esac
    else
      # Dry run - assume skip
      action="skip"
    fi

    if [[ "$action" == "overwrite" ]]; then
      if [[ $apply -eq 1 ]]; then
        mkdir -p "$target_path" || return 1
        if [[ $copy_mode -eq 1 ]]; then
          cp -p "$file" "$target_file" || return 1
          echo "♻️  Overwrote: $base → $organized_path/" >&2
          result_dest="$target_file"
          result_action="overwrote"
        else
          local source_dir="$(dirname "$file")"
          mv -f "$file" "$target_file" || return 1
          echo "♻️  Overwrote: $base → $organized_path/" >&2
          result_dest="$target_file"
          result_action="overwrote"
          cleanup_empty_parent_dirs "$source_dir"
        fi
      else
        echo "[DRY RUN] Would overwrite: $file → $target_file" >&2
        result_dest="$target_file"
        result_action="would_overwrite"
      fi
    else
      # Skip
      local size_mb=$(awk "BEGIN {printf \"%.1f\", $src_size / 1048576}")
      if [[ "$src_size" -eq "$dst_size" ]]; then
        echo "⏭️  Skipped (identical, ${size_mb} MB): $base" >&2
      else
        echo "⏭️  Skipped (user choice): $base" >&2
      fi
      result_dest="$target_file"
      result_action="skipped"
      # In move mode, remove source since dest has the file
      if [[ $copy_mode -eq 0 && $apply -eq 1 ]]; then
        local source_dir="$(dirname "$file")"
        rm "$file"
        cleanup_empty_parent_dirs "$source_dir"
      fi
      return 0
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
        printf "✅ Copied: %s → %s\n" "$display_source" "$abs_target" >&2
        result_dest="$abs_target"
        result_action="copied"
      else
        # Save the source directory before moving
        local source_dir="$(dirname "$file")"
        mv "$file" "$target_file" || return 1
        printf "✅ Moved: %s → %s\n" "$display_source" "$abs_target" >&2
        result_dest="$abs_target"
        result_action="moved"

        # Clean up empty parent directories after moving
        cleanup_empty_parent_dirs "$source_dir"
      fi
    else
      if [[ $copy_mode -eq 1 ]]; then
        printf "[DRY RUN] Would copy: %s → %s\n" "$display_source" "$abs_target" >&2
        result_dest="$abs_target"
        result_action="would_copy"
      else
        printf "[DRY RUN] Would move: %s → %s\n" "$display_source" "$abs_target" >&2
        result_dest="$abs_target"
        result_action="would_move"
      fi
    fi
  fi

  return 0
}

# Process the file
if ! process_file "$file"; then
  exit 1
fi

# Output machine-readable data to stdout (for parent scripts to capture)
# Prefixed with @@ to distinguish from human-readable output
echo "@@dest=$result_dest"
echo "@@action=$result_action"