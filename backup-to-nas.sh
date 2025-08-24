#!/bin/bash
set -euo pipefail

# Function to show usage
show_usage() {
    echo "Usage: $0 [--apply]"
    echo ""
    echo "Options:"
    echo "  --apply    Actually perform the backup (dry-run by default)"
    echo "  --help     Show this help message"
    echo ""
    echo "Without --apply, this script will show you what changes would be made"
    echo "without actually performing the backup."
}

# Parse command line arguments
APPLY_MODE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --apply)
            APPLY_MODE=true
            shift
            ;;
        --help|-h)
            show_usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

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
    echo "Copy .env.example to .env.local and configure your NAS settings"
    exit 1
fi

# Validate required environment variables
if [[ -z "${NAS_USER:-}" || -z "${NAS_HOST:-}" || -z "${NAS_BACKUP_PATH:-}" || -z "${SOURCE_PATH:-}" ]]; then
    echo "ERROR: Missing required environment variables"
    echo "Required: NAS_USER, NAS_HOST, NAS_BACKUP_PATH, SOURCE_PATH"
    echo "Check your .env.local file"
    exit 1
fi

# Set defaults
EXCLUSIONS_FILE="${EXCLUSIONS_FILE:-${HOME}/.exclusions.txt}"

if [[ "$APPLY_MODE" == "true" ]]; then
    echo "🔄 Starting backup to NAS..."
else
    echo "🔍 DRY RUN: Showing what would be backed up to NAS..."
    echo "Use --apply to actually perform the backup"
fi
echo "Source: $SOURCE_PATH"
echo "Destination: $NAS_USER@$NAS_HOST:$NAS_BACKUP_PATH"
echo "Exclusions: $EXCLUSIONS_FILE"
echo

# Check if exclusions file exists
if [[ ! -f "$EXCLUSIONS_FILE" ]]; then
    echo "⚠️  Exclusions file not found: $EXCLUSIONS_FILE"
    echo "Continuing without exclusions..."
    EXCLUDE_ARG=""
else
    EXCLUDE_ARG="--exclude-from=$EXCLUSIONS_FILE"
fi

# Build rsync command with appropriate flags
RSYNC_FLAGS="-avz --no-perms --no-owner --no-group --no-links --omit-dir-times --progress --stats --human-readable --size-only"

if [[ "$APPLY_MODE" == "false" ]]; then
    RSYNC_FLAGS="$RSYNC_FLAGS --dry-run"
fi

# Run rsync with environment variables
rsync $RSYNC_FLAGS $EXCLUDE_ARG "$SOURCE_PATH" "$NAS_USER@$NAS_HOST:$NAS_BACKUP_PATH" 2>&1 | grep -v "skipping non-regular file" || true

if [[ "$APPLY_MODE" == "true" ]]; then
    echo "✅ Backup completed successfully"
else
    echo "🔍 Dry run completed - no changes were made"
    echo "Run with --apply to perform the actual backup"
fi
