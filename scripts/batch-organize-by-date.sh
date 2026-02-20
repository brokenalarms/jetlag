#!/usr/bin/env bash
# batch-organize-by-date.sh
# Organizes all files in a directory into date-based subdirectories
# Usage: batch-organize-by-date.sh --source SOURCE_DIR --target TARGET_DIR [--apply]
# Uses filename date patterns first, falls back to creation time
# DRY-RUN by default; moves files only when --apply is present.

set -euo pipefail
IFS=$'\n\t'

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Initialize variables
apply=0
source_dir=""
target_dir=""
template=""
label=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) apply=1; shift ;;
    --source)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --source requires a directory path"; exit 1; }
      source_dir="$1"; shift ;;
    --target)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --target requires a directory path"; exit 1; }
      target_dir="$1"; shift ;;
    --template)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --template requires a template string"; exit 1; }
      template="$1"; shift ;;
    --label)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --label requires a label value"; exit 1; }
      label="$1"; shift ;;
    --help|-h)
      echo "Usage: batch-organize-by-date.sh --source SOURCE_DIR --target TARGET_DIR [OPTIONS]"
      echo "Options:"
      echo "  --source DIR      Directory containing files to organize"
      echo "  --target DIR      Target directory for organized files"
      echo "  --template TMPL   Path template (e.g., {{YYYY}}/{{label}}/{{YYYY}}-{{MM}}-{{DD}}/)"
      echo "  --label LABEL     Label value for {{label}} template variable"
      echo "  --apply           Apply changes (default: dry run)"
      echo "  --help, -h        Show this help"
      echo ""
      echo "Date extraction:"
      echo "  1. From filename patterns (VID_, IMG_, DJI_, etc.)"
      echo "  2. Fallback to file creation time"
      exit 0 ;;
    -*) echo "ERROR: Unknown option $1" >&2; exit 1 ;;
    *) echo "ERROR: Unexpected argument $1" >&2; exit 1 ;;
  esac
done

# Validate arguments
[[ -n "$source_dir" ]] || { echo "ERROR: --source is required" >&2; exit 1; }
[[ -d "$source_dir" ]] || { echo "ERROR: Source directory not found: $source_dir" >&2; exit 1; }
[[ -n "$target_dir" ]] || { echo "ERROR: --target is required" >&2; exit 1; }

# Expand tilde in paths
source_dir="${source_dir/#\~/$HOME}"
target_dir="${target_dir/#\~/$HOME}"

# Display configuration
echo "→ Source:  $source_dir"
echo "→ Target:  $target_dir"
echo "→ Mode:    $([[ $apply -eq 1 ]] && echo "APPLY (files will be moved)" || echo "DRY RUN (no changes)")"
echo

# Create target directory if it doesn't exist (for apply mode)
[[ $apply -eq 1 ]] && mkdir -p "$target_dir"

# Find all files to organize
files=()
while IFS= read -r -d '' file; do
  files+=("$file")
done < <(find "$source_dir" -type f ! -name ".*" -print0)

# Sort files alphabetically
IFS=$'\n' files=($(sort <<<"${files[*]}"))
unset IFS

total_files=${#files[@]}

if [[ $total_files -eq 0 ]]; then
  echo "No files to organize in $source_dir"
  exit 0
fi

echo "Found $total_files file(s) to organize"
echo

# Process each file using the single-file organize script
processed=0
succeeded=0
failed=0

for file in "${files[@]}"; do
  processed=$((processed + 1))
  base="$(basename "$file")"
  
  echo "[$processed/$total_files] Processing: $base"
  
  # Build arguments for single-file script
  args=("--target" "$target_dir")
  [[ -n "$template" ]] && args+=("--template" "$template")
  [[ -n "$label" ]] && args+=("--label" "$label")
  [[ $apply -eq 1 ]] && args+=("--apply")
  
  # Call the single-file organize script
  if "$SCRIPT_DIR/organize-by-date.sh" "$file" "${args[@]}"; then
    succeeded=$((succeeded + 1))
  else
    failed=$((failed + 1))
    echo "   ❌ Failed to organize $base"
  fi
done

# Summary
echo "=========================================="
echo "📊 BATCH ORGANIZATION SUMMARY"
echo "----------------------------------------"
echo "Total files processed: $processed"
echo "Successfully organized: $succeeded"
if [[ $failed -gt 0 ]]; then
  echo "Failed: $failed"
fi

if [[ $apply -eq 1 ]]; then
  echo "✅ Batch organization complete - changes applied."
else
  echo "✅ Batch organization complete - DRY RUN."
  echo "   Use --apply to execute the moves."
fi

# Exit with error if any files failed
[[ $failed -eq 0 ]] || exit 1