#!/usr/bin/env bash
# media-pipeline.sh
# Orchestrates video timestamp fixing and organization into date-based folders
# Usage: media-pipeline.sh --source SOURCE --target TARGET [--location LOCATION | --timezone +HHMM] [--apply]
# Processes all video files in SOURCE, fixes timestamps, then organizes by date into TARGET

set -euo pipefail
IFS=$'\n\t'

# Handle Ctrl-C gracefully
trap 'echo -e "\n\nInterrupted by user" >&2; exit 130' SIGINT

# Get script directory and load environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/lib-common.sh"
source "$SCRIPT_DIR/lib/lib-timestamp.sh"
load_env "$SCRIPT_DIR"

# Initialize variables
apply=0
verbose=0
source_dir=""
target_dir=""
profile=""
label=""
location_args=()

# No default location - always require CLI argument

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) apply=1; shift ;;
    --verbose|-v) verbose=1; shift ;;
    --profile)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --profile requires a profile name"; exit 1; }
      profile="$1"; shift ;;
    --source)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --source requires a directory path"; exit 1; }
      source_dir="$1"; shift ;;
    --target)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --target requires a directory path"; exit 1; }
      target_dir="$1"; shift ;;
    --location)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --location requires a location name/code"; exit 1; }
      location_args=("--location" "$1"); shift ;;
    --timezone)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --timezone requires +HHMM format"; exit 1; }
      # Validate timezone format: +HHMM or -HHMM
      if [[ ! "$1" =~ ^[+-][0-9]{4}$ ]]; then
        echo "ERROR: --timezone must be in +HHMM or -HHMM format (e.g., +0800, -0500)" >&2
        exit 1
      fi
      location_args=("--timezone" "$1"); shift ;;
    --label)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --label requires a label value"; exit 1; }
      label="$1"; shift ;;
    --help|-h)
      echo "Usage: media-pipeline.sh [--profile PROFILE | --source SOURCE --target TARGET] [OPTIONS]"
      echo "Options:"
      echo "  --profile NAME Profile from media-profiles.yaml (provides target, timezone)"
      echo "  --source DIR   Directory containing video files to process"
      echo "                     (default: current directory)"
      echo "  --target DIR   Target directory for organized files"
      echo "                     (overrides profile ready_dir)"
      echo "  --location NAME    Use location name/code for timezone lookup"
      echo "  --timezone TZ      Use specific timezone (+HHMM format, overrides profile)"
      echo "  --label LABEL      Label for template substitution (required)"
      echo "  --apply           Apply changes (default: dry run)"
      echo "  --verbose, -v     Show detailed processing info"
      echo "  --help, -h        Show this help"
      echo ""
      echo "Pipeline steps:"
      echo "  1. Fix video timestamps using metadata/filename patterns"
      echo "  2. Organize files into date-based directory structure"
      echo ""
      echo "Examples:"
      echo "  media-pipeline.sh --profile insta360 --label Taiwan --apply"
      echo "  media-pipeline.sh --source Exports --target Ready --timezone +0800 --label Taiwan"
      exit 0 ;;
    -*) echo "ERROR: Unknown option $1" >&2; exit 1 ;;
    *) echo "ERROR: Unexpected argument $1" >&2; exit 1 ;;
  esac
done

# Load profile if specified
if [[ -n "$profile" ]]; then
  profiles_file="$SCRIPT_DIR/media-profiles.yaml"
  if [[ ! -f "$profiles_file" ]]; then
    echo "ERROR: Profile file not found: $profiles_file" >&2
    exit 1
  fi

  # Activate venv if available for yaml support
  VENV="$SCRIPT_DIR/media-import"
  if [[ -d "$VENV" && -f "$VENV/bin/activate" ]]; then
    source "$VENV/bin/activate"
  fi

  # Parse profile using Python (yaml support)
  if ! profile_data=$(python3 -c "
import yaml, sys, os
try:
  with open('$profiles_file') as f:
    data = yaml.safe_load(f)
    if '$profile' not in data.get('profiles', {}):
      print('ERROR: Profile \"$profile\" not found', file=sys.stderr)
      sys.exit(1)
    p = data['profiles']['$profile']
    # Output: ready_dir
    print(f\"{p.get('ready_dir', '')}\")
except Exception as e:
  print(f'ERROR: {e}', file=sys.stderr)
  sys.exit(1)
"); then
    echo "Available profiles: $(python3 -c "import yaml; print(', '.join(yaml.safe_load(open('$profiles_file'))['profiles'].keys()))" || echo "Could not read profiles")" >&2
    exit 1
  fi

  profile_ready_dir="$profile_data"

  # Use profile ready_dir if not overridden
  # If ready_dir is not set or is "None" (from null), default to current directory
  if [[ -z "$target_dir" ]]; then
    if [[ -n "$profile_ready_dir" && "$profile_ready_dir" != "None" ]]; then
      target_dir="$profile_ready_dir"
    else
      target_dir="."
    fi
  fi
fi

# Validate arguments
[[ -n "$source_dir" ]] || source_dir="."
[[ -d "$source_dir" ]] || { echo "ERROR: Source directory not found: $source_dir" >&2; exit 1; }
[[ -n "$target_dir" ]] || { echo "ERROR: --target is required (or use --profile with ready_dir)" >&2; exit 1; }

# Validate label is provided
[[ -n "$label" ]] || { echo "ERROR: --label is required" >&2; exit 1; }

# Check for stale exiftool_tmp directories that would cause exiftool to fail
exiftool_tmp_dirs=$(find "$source_dir" -type d -name "exiftool_tmp" 2>/dev/null)
if [[ -n "$exiftool_tmp_dirs" ]]; then
  tmp_count=$(echo "$exiftool_tmp_dirs" | wc -l | tr -d ' ')
  echo "⚠️  Found $tmp_count stale exiftool_tmp director$([ "$tmp_count" -eq 1 ] && echo "y" || echo "ies") in source:" >&2
  echo "$exiftool_tmp_dirs" | sed 's/^/   /' >&2
  echo >&2
  read -p "Delete them? This will allow exiftool to run. (y/n) " -n 1 -r
  echo >&2
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    find "$source_dir" -type d -name "exiftool_tmp" -exec rm -rf {} + 2>/dev/null
    echo "✅ Deleted exiftool_tmp directories" >&2
  else
    echo "ERROR: Cannot proceed - exiftool will fail with these directories present" >&2
    exit 1
  fi
fi

# Helper functions
log_verbose() {
  [[ $verbose -eq 1 ]] && echo "$@" >&2
}

# Display configuration
echo "→ Source:  $source_dir"
echo "→ Target:  $target_dir"
echo "→ Mode:    $([[ $apply -eq 1 ]] && echo "APPLY (files will be processed)" || echo "DRY RUN (no changes)")"
if [[ ${#location_args[@]} -gt 0 ]]; then
  echo "→ Timezone: ${location_args[*]}"
else
  echo "→ Timezone: From video metadata (or will prompt if needed)"
fi
echo

# Create target directory if it doesn't exist (for apply mode)
[[ $apply -eq 1 ]] && mkdir -p "$target_dir"

# Find all video files to process
files=()
while IFS= read -r -d '' file; do
  files+=("$file")
done < <(find "$source_dir" -type f \( -iname "*.mp4" -o -iname "*.mov" -o -iname "*.insv" -o -iname "*.lrv" \) -print0)

# Sort files alphabetically
IFS=$'\n' files=($(sort <<<"${files[*]}"))
unset IFS

total_files=${#files[@]}

if [[ $total_files -eq 0 ]]; then
  echo "No video files found in $source_dir"
  exit 0
fi

echo "📹 Found $total_files video file(s) to process"
echo

# Process each file through the pipeline
processed=0
succeeded=0
changed=0
failed=0
failed_files=()

for file in "${files[@]}" ; do
  processed=$((processed + 1))
  base="$(basename "$file")"
  file_changed=0

  echo "[$processed/$total_files] Processing: $base"

  # Step 1: Tag media (must run before timestamp fixing as it changes file modified date)
  if [[ -n "$profile" ]]; then
    # Get tags and exif from profile for tagging
    tag_data=$(python3 -c "
import yaml
with open('$SCRIPT_DIR/media-profiles.yaml') as f:
  data = yaml.safe_load(f)
  p = data['profiles']['$profile']
  tags = ','.join(p.get('tags', []))
  exif = p.get('exif', {})
  make = exif.get('make', '')
  model = exif.get('model', '')
  print(f'{tags}|{make}|{model}')
")

    IFS='|' read -r tags make model <<< "$tag_data"

    if [[ -n "$tags" || -n "$make" || -n "$model" ]]; then
      echo "🏷️  Checking tags..."
      cmd=("$SCRIPT_DIR/tag-media.py" "$file")
      [[ -n "$tags" ]] && cmd+=("--tags" "$tags")
      [[ -n "$make" ]] && cmd+=("--make" "$make")
      [[ -n "$model" ]] && cmd+=("--model" "$model")
      [[ $apply -eq 1 ]] && cmd+=("--apply")
      tag_output=$("${cmd[@]}" 2>&1)
      echo "$tag_output" | sed 's/^/  /'
      # Check if tags were changed (output contains "Tagged:" or "EXIF:" but not "Already tagged")
      if [[ "$tag_output" =~ (📌|Tagged:|EXIF:) ]] && [[ ! "$tag_output" =~ "Already tagged correctly" ]]; then
        file_changed=1
      fi
    fi
  fi

  # Step 2: Fix video timestamp
  echo "🔧 Fixing timestamp..."

  # Build arguments for fix-video-timestamp.sh
  fix_args=()
  [[ $apply -eq 1 ]] && fix_args+=("--apply")
  [[ $verbose -eq 1 ]] && fix_args+=("--verbose")
  if [[ ${#location_args[@]} -gt 0 ]]; then
    fix_args+=("${location_args[@]}")
  fi

  fix_output=$("$SCRIPT_DIR/fix-media-timestamp.sh" "$file" "${fix_args[@]+"${fix_args[@]}"}" 2>&1)
  fix_rc=$?
  echo "$fix_output" | sed 's/^/  /'

  if [[ $fix_rc -ne 0 ]]; then
    echo "   ❌ Timestamp fix failed for $base"
    failed=$((failed + 1))
    failed_files+=("$base")
    echo  # Empty line between files
    continue
  fi

  # Check if timestamp was changed (output contains checkmark or "Updated" but not "No change needed")
  if [[ "$fix_output" =~ (✅|Updated|Written) ]] && [[ ! "$fix_output" =~ "No change needed" ]]; then
    file_changed=1
  fi

  # Step 3: Organize by date
  echo "📁 Organizing by date..."

  # Build arguments for organize-by-date.sh
  org_args=("--target" "$target_dir")
  [[ $apply -eq 1 ]] && org_args+=("--apply")
  [[ $verbose -eq 1 ]] && org_args+=("--verbose")

  # Pass raw template and label separately
  if [[ -n "$MEDIA_PIPELINE_TEMPLATE" ]]; then
    template="$MEDIA_PIPELINE_TEMPLATE"
  else
    template="{{YYYY}}-{{MM}}-{{DD}}"
  fi
  org_args+=("--template" "$template")
  org_args+=("--label" "$label")

  org_output=$("$SCRIPT_DIR/organize-by-date.sh" "$file" "${org_args[@]+"${org_args[@]}"}" 2>&1)
  org_rc=$?
  echo "$org_output" | sed 's/^/  /'

  if [[ $org_rc -ne 0 ]]; then
    echo "   ❌ Organization failed for $base"
    failed=$((failed + 1))
    failed_files+=("$base")
  else
    succeeded=$((succeeded + 1))
    # Check if file was moved (output contains "Moved:" or "Copied:" but not "Already organized")
    if [[ "$org_output" =~ (✅\ Moved:|✅\ Copied:) ]]; then
      file_changed=1
    fi
  fi

  # Increment changed counter if any step changed the file
  [[ $file_changed -eq 1 ]] && changed=$((changed + 1))

  echo  # Empty line between files
done

# Clean up empty directories in source (only in apply mode)
if [[ $apply -eq 1 ]]; then
  find "$source_dir" -type d -empty -delete 2>/dev/null || true
fi

# Summary
echo
echo "==========================================="
echo "📊 MEDIA PIPELINE SUMMARY"
echo "-------------------------------------------"
echo "Total files processed: $processed"
echo "Successfully completed: $succeeded"
echo "Files changed: $changed"
echo "Files unchanged: $((succeeded - changed))"
if [[ $failed -gt 0 ]]; then
  echo "Failed: $failed"
  echo ""
  echo "Failed files:"
  for failed_file in "${failed_files[@]}"; do
    echo "  - $failed_file"
  done
fi

if [[ $apply -eq 1 ]]; then
  echo "✅ Media pipeline complete - changes applied."
else
  echo "✅ Media pipeline complete - DRY RUN."
  echo "   Use --apply to execute timestamp fixes and file organization."
fi

# Exit with error if any files failed
[[ $failed -eq 0 ]] || exit 1