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
  profile_data=$(python3 -c "
import yaml, sys, os
try:
  with open('$profiles_file') as f:
    data = yaml.safe_load(f)
    if '$profile' not in data.get('profiles', {}):
      print('ERROR: Profile \"$profile\" not found', file=sys.stderr)
      sys.exit(1)
    p = data['profiles']['$profile']
    # Output: ready_dir|timezone
    print(f\"{p.get('ready_dir', '')}|{p.get('timezone', '')}\")
except Exception as e:
  print(f'ERROR: {e}', file=sys.stderr)
  sys.exit(1)
" 2>&1)

  exit_code=$?
  if [[ $exit_code -ne 0 ]]; then
    echo "$profile_data" >&2
    echo "Available profiles: $(python3 -c "import yaml; print(', '.join(yaml.safe_load(open('$profiles_file'))['profiles'].keys()))" 2>/dev/null || echo "Could not read profiles")" >&2
    exit 1
  fi

  IFS='|' read -r profile_ready_dir profile_timezone <<< "$profile_data"

  # Use profile values if not overridden
  [[ -z "$target_dir" && -n "$profile_ready_dir" ]] && target_dir="$profile_ready_dir"
  [[ ${#location_args[@]} -eq 0 && -n "$profile_timezone" ]] && location_args=("--timezone" "$profile_timezone")
fi

# Validate arguments
[[ -n "$source_dir" ]] || source_dir="."
[[ -d "$source_dir" ]] || { echo "ERROR: Source directory not found: $source_dir" >&2; exit 1; }
[[ -n "$target_dir" ]] || { echo "ERROR: --target is required (or use --profile with ready_dir)" >&2; exit 1; }

# Validate label is provided
[[ -n "$label" ]] || { echo "ERROR: --label is required" >&2; exit 1; }

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

total_files=${#files[@]}

if [[ $total_files -eq 0 ]]; then
  echo "No video files found in $source_dir"
  exit 0
fi

echo "📹 Found $total_files video file(s) to process"
echo

# Set batch mode for fix-video-timestamp.sh to suppress completion messages
export BATCH_MODE=1

# Process each file through the pipeline
processed=0
succeeded=0
failed=0

for file in "${files[@]}" ; do
  processed=$((processed + 1))
  base="$(basename "$file")"
  
  echo "[$processed/$total_files] Processing: $base"
  
  # Step 1: Fix video timestamp
  echo "  🔧 Fixing timestamp..."
  
  # Build arguments for fix-video-timestamp.sh
  fix_args=()
  [[ $apply -eq 1 ]] && fix_args+=("--apply")
  [[ $verbose -eq 1 ]] && fix_args+=("--verbose")
  if [[ ${#location_args[@]} -gt 0 ]]; then
    fix_args+=("${location_args[@]}")
  fi
  
  if ! "$SCRIPT_DIR/fix-media-timestamp.sh" "$file" "${fix_args[@]+"${fix_args[@]}"}"; then
    echo "   ❌ Timestamp fix failed for $base"
    failed=$((failed + 1))
    echo  # Empty line between files
    continue
  fi
  
  # Step 2: Organize by date
  echo "  📁 Organizing by date..."
  
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
  
  if ! "$SCRIPT_DIR/organize-by-date.sh" "$file" "${org_args[@]+"${org_args[@]}"}"; then
    echo "   ❌ Organization failed for $base"
    failed=$((failed + 1))
  else
    succeeded=$((succeeded + 1))
  fi
  
  echo  # Empty line between files
done

# Summary
echo "==========================================="
echo "📊 MEDIA PIPELINE SUMMARY"
echo "-------------------------------------------"
echo "Total files processed: $processed"
echo "Successfully completed: $succeeded"
if [[ $failed -gt 0 ]]; then
  echo "Failed: $failed"
fi

if [[ $apply -eq 1 ]]; then
  echo "✅ Media pipeline complete - changes applied."
else
  echo "✅ Media pipeline complete - DRY RUN."
  echo "   Use --apply to execute timestamp fixes and file organization."
fi

# Exit with error if any files failed
[[ $failed -eq 0 ]] || exit 1