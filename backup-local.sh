#!/bin/bash
set -euo pipefail

# Get script directory for loading environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load environment variables from .env.local
if [[ -f "$SCRIPT_DIR/.env.local" ]]; then
    # Source the file directly (bash will ignore comments)
    set -a  # Export all variables
    source "$SCRIPT_DIR/.env.local"
    set +a  # Stop exporting
else
    echo "ERROR: .env.local not found"
    echo "Copy .env.example to .env.local and configure your backup paths"
    exit 1
fi

# Default to dry run unless --apply is specified
DRY_RUN=1
VERBOSE=0

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) 
      DRY_RUN=0
      shift ;;
    --verbose|-v) 
      VERBOSE=1
      shift ;;
    --help|-h)
      echo "Usage: backup-local.sh [OPTIONS]"
      echo "Local backup using paths configured in .env.local"
      echo ""
      echo "Options:"
      echo "  --apply         Actually perform the backup (default: dry run)"
      echo "  --verbose, -v   Show verbose output"
      echo "  --help, -h      Show this help"
      echo ""
      echo "Configuration:"
      echo "  Backup paths are configured in .env.local:"
      echo "    SOURCE_PATH      - Source directory to backup"
      echo "    LOCAL_BACKUP_PATH - Local destination directory"
      echo "    EXCLUSIONS_FILE  - File containing rsync exclusions"
      exit 0 ;;
    *)
      echo "ERROR: Unknown option $1" >&2
      echo "Use --help for usage information" >&2
      exit 1 ;;
  esac
done

# Validate required environment variables
if [[ -z "${SOURCE_PATH:-}" || -z "${LOCAL_BACKUP_PATH:-}" ]]; then
    echo "ERROR: Missing required environment variables"
    echo "Required: SOURCE_PATH, LOCAL_BACKUP_PATH"
    echo "Check your .env.local file"
    exit 1
fi

# Set paths from environment
SOURCE="$SOURCE_PATH"
DEST="$LOCAL_BACKUP_PATH"
EXCLUSIONS="${EXCLUSIONS_FILE:-${HOME}/.exclusions.txt}"

# Check if volumes are mounted
if [[ ! -d "$SOURCE" ]]; then
  echo "ERROR: Source volume not found: $SOURCE" >&2
  exit 1
fi

if [[ ! -d "$DEST" ]]; then
  echo "ERROR: Destination volume not found: $DEST" >&2
  exit 1
fi

echo "📁 Local Backup"
echo "Source:      $SOURCE"
echo "Destination: $DEST"
echo "Exclusions:  $EXCLUSIONS"

# Check if exclusions file exists
if [[ ! -f "$EXCLUSIONS" ]]; then
  echo "⚠️  Exclusions file not found: $EXCLUSIONS"
  echo "Continuing without exclusions..."
  EXCLUDE_ARGS=""
else
  EXCLUDE_ARGS="--exclude-from=$EXCLUSIONS"
fi

# Build rsync command
RSYNC_ARGS="-avz --delete-during --force-delete --ignore-errors --no-perms --no-owner --no-group --no-links --omit-dir-times --stats"

if [[ $DRY_RUN -eq 1 ]]; then
  echo "Mode:        DRY RUN (no changes will be made)"
  echo "Use --apply to perform actual backup"
  RSYNC_ARGS="$RSYNC_ARGS --dry-run"
else
  echo "Mode:        APPLYING CHANGES"
fi

echo ""

# Add verbosity
if [[ $VERBOSE -eq 1 ]]; then
  RSYNC_ARGS="$RSYNC_ARGS --info=name"
else
  RSYNC_ARGS="$RSYNC_ARGS --info=progress2"
fi

# Run rsync
echo "🔄 Starting backup..."
if [[ $DRY_RUN -eq 1 ]]; then
  echo "(This is a dry run - no files will be copied)"
  echo ""
fi

rsync $RSYNC_ARGS $EXCLUDE_ARGS "$SOURCE" "$DEST" 2>&1 | grep -v "skipping non-regular file" || true

echo ""
if [[ $DRY_RUN -eq 1 ]]; then
  echo "🧪 Dry run completed. Use --apply to perform the actual backup."
else
  echo "✅ Backup completed successfully"
fi
