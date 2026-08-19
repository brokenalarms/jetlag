#!/bin/bash
# strip-date-prefix.sh
# Removes incorrectly prepended date prefixes from filenames
# Pattern: YYYY-MM-DD - filename.ext → filename.ext
# Supports nested subdirectories

set -euo pipefail
IFS=$'\n\t'

# Initialize variables
apply=0
source_dir=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) apply=1; shift ;;
    --source)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --source requires a directory path"; exit 1; }
      source_dir="$1"; shift ;;
    --help|-h)
      echo "Usage: strip-date-prefix.sh --source SOURCE_DIR [--apply]"
      echo "Options:"
      echo "  --source DIR   Directory containing files to process"
      echo "  --apply        Apply changes (default: dry run)"
      echo "  --help, -h     Show this help"
      echo ""
      echo "Removes date prefixes matching patterns:"
      echo "  - YYYY-MM-DD - filename.ext"
      echo "  - YYYYMMDD-filename.ext"
      exit 0 ;;
    -*) echo "ERROR: Unknown option $1" >&2; exit 1 ;;
    *) 
      [[ -z "$source_dir" ]] || { echo "ERROR: Only --source directory allowed" >&2; exit 1; }
      source_dir="$1"; shift ;;
  esac
done

# Validate arguments
[[ -n "$source_dir" ]] || { echo "ERROR: --source is required" >&2; exit 1; }
[[ -d "$source_dir" ]] || { echo "ERROR: Source directory not found: $source_dir" >&2; exit 1; }

# Display configuration
echo "→ Source:  $source_dir"
echo "→ Mode:    $([[ $apply -eq 1 ]] && echo "APPLY (files will be renamed)" || echo "DRY RUN (no changes)")"
echo

# Find all files with date prefix patterns
files=()
while IFS= read -r -d '' file; do
  base="$(basename "$file")"
  # Check if filename matches either pattern: YYYY-MM-DD - * or YYYYMMDD-*
  if [[ "$base" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}\ -\ .+ ]] || [[ "$base" =~ ^[0-9]{8}-.+ ]]; then
    files+=("$file")
  fi
done < <(find "$source_dir" -type f -print0)

total_files=${#files[@]}

if [[ $total_files -eq 0 ]]; then
  echo "No files found with date prefix patterns (YYYY-MM-DD - or YYYYMMDD-)"
  exit 0
fi

echo "Found $total_files file(s) with date prefixes to strip"
echo

# Process each file
processed=0
succeeded=0
failed=0

for file in "${files[@]}"; do
  processed=$((processed + 1))
  base="$(basename "$file")"
  dir="$(dirname "$file")"
  
  # Determine pattern and strip appropriate prefix
  if [[ "$base" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}\ -\  ]]; then
    # Pattern: YYYY-MM-DD - filename
    new_base="${base#????-??-?? - }"
    pattern="YYYY-MM-DD - "
  elif [[ "$base" =~ ^[0-9]{8}- ]]; then
    # Pattern: YYYYMMDD-filename
    new_base="${base#????????-}"
    pattern="YYYYMMDD-"
  else
    echo "   ⚠️  Unexpected pattern: $base"
    failed=$((failed + 1))
    continue
  fi
  
  new_file="$dir/$new_base"
  
  echo "[$processed/$total_files] $base → $new_base (pattern: $pattern)"
  
  if [[ $apply -eq 1 ]]; then
    if [[ -e "$new_file" ]]; then
      echo "   ⚠️  Target exists, skipping: $new_base"
      failed=$((failed + 1))
    else
      if mv "$file" "$new_file" 2>/dev/null; then
        echo "   ✅ Renamed"
        succeeded=$((succeeded + 1))
      else
        echo "   ❌ Failed to rename"
        failed=$((failed + 1))
      fi
    fi
  else
    echo "   [DRY RUN] Would rename"
    succeeded=$((succeeded + 1))
  fi
done

# Summary
echo
echo "=========================================="
echo "📊 STRIP DATE PREFIX SUMMARY"
echo "----------------------------------------"
echo "Total files processed: $processed"
echo "Successfully processed: $succeeded"
if [[ $failed -gt 0 ]]; then
  echo "Failed/Skipped: $failed"
fi

if [[ $apply -eq 1 ]]; then
  echo "✅ Date prefix stripping complete - changes applied."
else
  echo "✅ Date prefix stripping complete - DRY RUN."
  echo "   Use --apply to execute the renames."
fi

# Exit with error if any files failed
[[ $failed -eq 0 ]] || exit 1