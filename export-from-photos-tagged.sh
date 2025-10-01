#!/usr/bin/env bash
# export-from-photos-tagged.sh
# Export photos/videos from Photos app with Finder tags, then organize using templates
# Workflow: Photos app tagging → osxphotos export → organize-by-date organization

set -euo pipefail
IFS=$'\n\t'

# Get script directory for loading environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load environment variables if available
if [[ -f "${SCRIPT_DIR}/.env.local" ]]; then
  source "${SCRIPT_DIR}/.env.local"
elif [[ -f "./.env.local" ]]; then
  source "./.env.local"
fi

# Initialize variables
apply=0
keyword=""
temp_dir=""
final_target=""
label=""
cleanup=1

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) apply=1; shift ;;
    --keyword)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --keyword requires a keyword value"; exit 1; }
      keyword="$1"; shift ;;
    --temp-dir)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --temp-dir requires a directory path"; exit 1; }
      temp_dir="$1"; shift ;;
    --target)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --target requires a directory path"; exit 1; }
      final_target="$1"; shift ;;
    --label)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --label requires a label value"; exit 1; }
      label="$1"; shift ;;
    --no-cleanup)
      cleanup=0; shift ;;
    --help|-h)
      echo "Usage: export-from-photos-tagged.sh --keyword KEYWORD --target TARGET_DIR [OPTIONS]"
      echo ""
      echo "Workflow:"
      echo "  1. Export photos/videos with specific keyword from Photos app"
      echo "  2. Preserve Finder tags from Photos keywords and persons"
      echo "  3. Organize exported files using date-based templates"
      echo "  4. Optionally clean up temporary export directory"
      echo ""
      echo "Required:"
      echo "  --keyword WORD      Photos keyword to export (e.g., 'ReadyForFCP', 'Taiwan-Export')"
      echo "  --target DIR        Final organized destination directory"
      echo ""
      echo "Options:"
      echo "  --label LABEL       Label for organization template (default: keyword)"
      echo "  --temp-dir DIR      Temporary export directory (default: ~/Desktop/photos-export-tmp)"
      echo "  --no-cleanup        Keep temporary export directory after processing"
      echo "  --apply             Apply changes (default: dry run)"
      echo "  --help, -h          Show this help"
      echo ""
      echo "Prerequisites:"
      echo "  - osxphotos installed: pip install osxphotos"
      echo "  - Photos app keyword tagging completed"
      echo "  - MEDIA_PIPELINE_TEMPLATE set in .env.local"
      echo ""
      echo "Examples:"
      echo "  # Tag videos in Photos with 'Taiwan-FCP', then:"
      echo "  $0 --keyword 'Taiwan-FCP' --target '/Volumes/External/FCP-Videos' --label 'Taiwan Trip'"
      echo "  $0 --keyword 'ReadyForFCP' --target '/Volumes/External/FCP-Videos' --apply"
      exit 0 ;;
    -*) echo "ERROR: Unknown option $1" >&2; exit 1 ;;
    *) echo "ERROR: Unexpected argument $1" >&2; exit 1 ;;
  esac
done

# Validate required arguments
[[ -n "$keyword" ]] || { echo "ERROR: --keyword is required" >&2; exit 1; }
[[ -n "$final_target" ]] || { echo "ERROR: --target is required" >&2; exit 1; }

# Set defaults
if [[ -z "$label" ]]; then
  label="$keyword"
fi

if [[ -z "$temp_dir" ]]; then
  temp_dir="$HOME/Desktop/photos-export-tmp"
fi

# Expand tilde in paths
temp_dir="${temp_dir/#\~/$HOME}"
final_target="${final_target/#\~/$HOME}"

# Check for osxphotos
if ! command -v osxphotos &> /dev/null; then
  echo "ERROR: osxphotos not found" >&2
  echo "Install with: pip install osxphotos" >&2
  exit 1
fi

# Check for MEDIA_PIPELINE_TEMPLATE
if [[ -z "${MEDIA_PIPELINE_TEMPLATE:-}" ]]; then
  echo "ERROR: MEDIA_PIPELINE_TEMPLATE not found in environment" >&2
  echo "Please set it in .env.local (e.g., MEDIA_PIPELINE_TEMPLATE=\"{{YYYY}}/{{label}}/{{YYYY}}-{{MM}}-{{DD}}/\")" >&2
  exit 1
fi

# Display configuration
echo "🏷️  PHOTOS EXPORT & ORGANIZATION"
echo "→ Keyword:        $keyword"
echo "→ Temp Export:    $temp_dir"
echo "→ Final Target:   $final_target"
echo "→ Label:          $label"
echo "→ Template:       $MEDIA_PIPELINE_TEMPLATE"
echo "→ Cleanup Temp:   $([[ $cleanup -eq 1 ]] && echo "Yes" || echo "No")"
echo "→ Mode:           $([[ $apply -eq 1 ]] && echo "APPLY" || echo "DRY RUN")"
echo

# Create temp directory
if [[ $apply -eq 1 ]]; then
  mkdir -p "$temp_dir"
fi

# Step 1: Export from Photos using osxphotos
echo "📤 Step 1: Exporting from Photos app..."
if [[ $apply -eq 1 ]]; then
  osxphotos_cmd=(
    osxphotos export "$temp_dir"
    --keyword "$keyword"
    --finder-tag-keywords
    --finder-tag-persons
    --merge-exif-keywords
    --merge-exif-persons
    --touch-file
    --strip
    --exiftool
    --description "{title}{newline}{descr}"
    --finder-comment "{title}{newline}{descr}"
    --update
    --verbose
  )

  echo "Running: ${osxphotos_cmd[*]}"
  "${osxphotos_cmd[@]}"

  # Check if any files were exported
  exported_count=$(find "$temp_dir" -type f ! -name ".*" | wc -l | tr -d ' ')
  echo "✅ Exported $exported_count files to temporary directory"

  if [[ $exported_count -eq 0 ]]; then
    echo "⚠️  No files exported. Check if keyword '$keyword' exists in Photos." >&2
    exit 1
  fi
else
  echo "[DRY RUN] Would export files with keyword '$keyword' to $temp_dir"
fi

echo

# Step 2: Organize exported files
echo "📁 Step 2: Organizing exported files..."
batch_script="$SCRIPT_DIR/batch-organize-by-date.sh"
[[ -x "$batch_script" ]] || {
  echo "ERROR: $batch_script not found or not executable" >&2
  exit 1
}

# Build arguments for batch-organize-by-date.sh
args=("--source" "$temp_dir" "--target" "$final_target" "--template" "$MEDIA_PIPELINE_TEMPLATE" "--label" "$label")
[[ $apply -eq 1 ]] && args+=("--apply")

echo "Running organization: $batch_script ${args[*]}"
"$batch_script" "${args[@]}"

# Step 3: Cleanup
if [[ $cleanup -eq 1 && $apply -eq 1 ]]; then
  echo
  echo "🧹 Step 3: Cleaning up temporary directory..."
  if [[ -d "$temp_dir" ]]; then
    echo "Removing: $temp_dir"
    rm -rf "$temp_dir"
    echo "✅ Cleanup complete"
  fi
elif [[ $cleanup -eq 1 ]]; then
  echo
  echo "[DRY RUN] Would clean up temporary directory: $temp_dir"
fi

echo
echo "✅ Photos export and organization complete!"
if [[ $apply -eq 0 ]]; then
  echo "   Use --apply to execute the export and organization."
fi