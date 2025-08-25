#!/bin/bash
set -euo pipefail

# Get script directory for loading environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source common rsync functions
source "$SCRIPT_DIR/rsync-common.sh"

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
while [[ $# -gt 0 ]]; do
    case $1 in
        --apply)
            DRY_RUN=0
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

# Set default dry run if not set
DRY_RUN="${DRY_RUN:-1}"

# Load environment variables
load_env "$SCRIPT_DIR" || exit 1

# Validate required environment variables
if [[ -z "${NAS_USER:-}" || -z "${NAS_HOST:-}" || -z "${NAS_BACKUP_PATH:-}" || -z "${SOURCE_PATH:-}" ]]; then
    echo "ERROR: Missing required environment variables"
    echo "Required: NAS_USER, NAS_HOST, NAS_BACKUP_PATH, SOURCE_PATH"
    echo "Check your .env.local file"
    exit 1
fi

# Set paths from environment
SOURCE="$SOURCE_PATH"
DEST="${NAS_USER}@${NAS_HOST}:${NAS_BACKUP_PATH}"
EXCLUSIONS="${EXCLUSIONS_FILE:-${HOME}/.exclusions.txt}"

# Validate source path exists
if [[ ! -d "$SOURCE" ]]; then
    echo "ERROR: Source folder not found: $SOURCE" >&2
    exit 1
fi

if [[ "$DRY_RUN" -eq 0 ]]; then
    echo "🔄 Starting backup to NAS..."
else
    echo "🔍 DRY RUN: Showing what would be backed up to NAS..."
    echo "Use --apply to actually perform the backup"
fi
echo "Source: $SOURCE"
echo "Destination: $DEST"
echo "Exclusions: $EXCLUSIONS"
echo

# Run rsync using the common function
# No delete by default (incremental backup)
run_rsync "$SOURCE" "$DEST" "$DRY_RUN" "$EXCLUSIONS"