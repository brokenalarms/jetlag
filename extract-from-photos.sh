#!/usr/bin/env bash
# extract-from-photos.sh
# Extracts media from macOS Photos app to organized directory structure
# Usage: extract-from-photos.sh --label LABEL --target TARGET_DIR [--apply]
# Uses MEDIA_PIPELINE_TEMPLATE from .env.local for organization

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
label=""
target_dir=""
photos_library=""
album=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) apply=1; shift ;;
    --label)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --label requires a label value"; exit 1; }
      label="$1"; shift ;;
    --target)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --target requires a directory path"; exit 1; }
      target_dir="$1"; shift ;;
    --photos-library)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --photos-library requires a path"; exit 1; }
      photos_library="$1"; shift ;;
    --album)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --album requires a path to exported album"; exit 1; }
      album="$1"; shift ;;
    --help|-h)
      echo "Usage: extract-from-photos.sh --label LABEL --target TARGET_DIR [OPTIONS]"
      echo "Options:"
      echo "  --label LABEL       Label for organization (e.g., 'iPhone Import')"
      echo "  --target DIR        Target directory for organized files"
      echo "  --photos-library PATH  Photos library path (default: ~/Pictures/Photos Library.photoslibrary)"
      echo "  --album PATH        Path to exported album directory"
      echo "  --apply             Apply changes (default: dry run)"
      echo "  --help, -h          Show this help"
      echo ""
      echo "Organization uses MEDIA_PIPELINE_TEMPLATE from .env.local:"
      echo "  Current template: ${MEDIA_PIPELINE_TEMPLATE:-"{{YYYY}}/{{label}}/{{YYYY}}-{{MM}}-{{DD}}/"}"
      echo ""
      echo "Album workflow:"
      echo "  1. In Photos app: select album → File → Export → Export [N] Photos"
      echo "  2. Export to any directory (e.g., ~/Downloads/Korea-Trip/)"
      echo "  3. Run: $0 --album /path/to/exported/album --label 'Album Name' --target /path/"
      echo ""
      echo "Examples:"
      echo "  $0 --label 'iPhone Import' --target '/Volumes/Media/Photos/'"
      echo "  $0 --album '~/Downloads/Korea-Trip' --label 'Korea 2025' --target . --apply"
      exit 0 ;;
    -*) echo "ERROR: Unknown option $1" >&2; exit 1 ;;
    *) echo "ERROR: Unexpected argument $1" >&2; exit 1 ;;
  esac
done

# Validate required arguments
[[ -n "$label" ]] || { echo "ERROR: --label is required" >&2; exit 1; }
[[ -n "$target_dir" ]] || { echo "ERROR: --target is required" >&2; exit 1; }

# Expand tilde in target directory
target_dir="${target_dir/#\~/$HOME}"

# Handle album vs full library extraction
if [[ -n "$album" ]]; then
  # Album mode - use provided path to exported album
  # Expand tilde if present
  album_dir="${album/#\~/$HOME}"
  if [[ ! -d "$album_dir" ]]; then
    echo "ERROR: Album directory not found at: $album_dir" >&2
    echo "" >&2
    echo "To extract a specific album:" >&2
    echo "1. Open Photos app" >&2
    echo "2. Select the album" >&2
    echo "3. Select all photos (Cmd+A)" >&2
    echo "4. File → Export → Export [N] Photos" >&2
    echo "5. Export to any directory" >&2
    echo "6. Run: $0 --album /path/to/exported/directory --label 'Label' --target /path/" >&2
    exit 1
  fi
  source_dir="$album_dir"
else
  # Full library mode
  # Default Photos library location
  if [[ -z "$photos_library" ]]; then
    photos_library="$HOME/Pictures/Photos Library.photoslibrary"
  fi

  # Validate Photos library exists
  [[ -d "$photos_library" ]] || { echo "ERROR: Photos library not found at: $photos_library" >&2; exit 1; }

  # Try to find media directories in Photos library
  # Modern Photos libraries use "originals" directory structure
  originals_dir="$photos_library/originals"
  masters_dir="$photos_library/Masters"

  if [[ -d "$originals_dir" ]]; then
    source_dir="$originals_dir"
    echo "→ Using modern Photos library format (originals)"
  elif [[ -d "$masters_dir" ]]; then
    source_dir="$masters_dir"
    echo "→ Using legacy Photos library format (Masters)"
  else
    echo "ERROR: Cannot find media files in Photos library" >&2
    echo "Checked:" >&2
    echo "  Modern: $originals_dir" >&2
    echo "  Legacy: $masters_dir" >&2
    echo "" >&2
    echo "The Photos library may use a different internal structure." >&2
    echo "Consider using album export instead:" >&2
    echo "  1. Export album from Photos app to a directory" >&2
    echo "  2. Use: $0 --album /path/to/exported/album --label 'Label' --target /path/" >&2
    exit 1
  fi
fi

# Check for MEDIA_PIPELINE_TEMPLATE
if [[ -z "${MEDIA_PIPELINE_TEMPLATE:-}" ]]; then
  echo "ERROR: MEDIA_PIPELINE_TEMPLATE not found in environment" >&2
  echo "Please set it in .env.local (e.g., MEDIA_PIPELINE_TEMPLATE=\"{{YYYY}}/{{label}}/{{YYYY}}-{{MM}}-{{DD}}/\")" >&2
  exit 1
fi

# Display configuration
if [[ -n "$album" ]]; then
  echo "→ Source Mode:    Album export"
  echo "→ Album Path:     $album_dir"
  echo "→ Source Dir:     $source_dir"
else
  echo "→ Source Mode:    Full Photos library"
  echo "→ Photos Library: $photos_library"
  echo "→ Source Dir:     $source_dir"
fi
echo "→ Target:         $target_dir"
echo "→ Label:          $label"
echo "→ Template:       $MEDIA_PIPELINE_TEMPLATE"
echo "→ Mode:           $([[ $apply -eq 1 ]] && echo "APPLY (files will be moved)" || echo "DRY RUN (no changes)")"
echo

# Check if batch-organize-by-date.sh exists
batch_script="$SCRIPT_DIR/batch-organize-by-date.sh"
[[ -x "$batch_script" ]] || {
  echo "ERROR: $batch_script not found or not executable" >&2
  exit 1
}

# Build arguments for batch-organize-by-date.sh
args=("--source" "$source_dir" "--target" "$target_dir" "--template" "$MEDIA_PIPELINE_TEMPLATE" "--label" "$label")
[[ $apply -eq 1 ]] && args+=("--apply")

# Check if source directory has files
file_count=$(find "$source_dir" -type f ! -name ".*" | wc -l | tr -d ' ')
if [[ $file_count -eq 0 ]]; then
  echo "WARNING: No files found in source directory: $source_dir"
  exit 1
fi

echo "→ Found:          $file_count files"
echo

# Execute the batch organization
exec "$batch_script" "${args[@]}"