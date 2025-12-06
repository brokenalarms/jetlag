#!/bin/bash
set -euo pipefail

# Get script directory for loading environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source common libraries
source "$SCRIPT_DIR/lib/lib-common.sh"
source "$SCRIPT_DIR/lib/lib-sync.sh"

# Function to show help
show_help() {
    echo "Usage: sync-local.sh [OPTIONS]"
    echo "Local backup using paths configured in .env.local"
    echo ""
    echo "Options:"
    echo "  --apply         Actually perform the backup (default: dry run)"
    echo "  --help, -h      Show this help"
    echo ""
    echo "Configuration:"
    echo "  Backup paths are configured in .env.local:"
    echo "    SOURCE_PATH      - Source directory to backup"
    echo "    LOCAL_SYNC_PATH  - Local destination directory"
    echo "    EXCLUSIONS_FILE  - File containing rsync exclusions"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --apply) 
            DRY_RUN=0
            shift ;;
        --help|-h)
            show_help
            exit 0 ;;
        *)
            echo "ERROR: Unknown option $1" >&2
            echo "Use --help for usage information" >&2
            exit 1 ;;
    esac
done

# Set default dry run if not set
DRY_RUN="${DRY_RUN:-1}"

# Load environment variables
load_env "$SCRIPT_DIR" || exit 1

# Validate required environment variables
if [[ -z "${SOURCE_PATH:-}" || -z "${LOCAL_SYNC_PATH:-}" ]]; then
    echo "ERROR: Missing required environment variables"
    echo "Required: SOURCE_PATH, LOCAL_SYNC_PATH"
    echo "Check your .env.local file"
    exit 1
fi

# Set paths from environment
SOURCE="$SOURCE_PATH"
DEST="$LOCAL_SYNC_PATH"
EXCLUSIONS="${EXCLUSIONS_FILE:-${HOME}/.exclusions.txt}"

# Validate paths exist
validate_paths "$SOURCE" "$DEST" || exit 1

echo "📁 Local Backup" >&2
echo "Source:      $SOURCE" >&2
echo "Destination: $DEST" >&2
echo "Exclusions:  $EXCLUSIONS" >&2

if [[ $DRY_RUN -eq 1 ]]; then
    echo "Mode:        DRY RUN (no changes will be made)" >&2
    echo "Use --apply to perform actual backup" >&2
else
    echo "Mode:        APPLYING CHANGES" >&2
fi

echo "" >&2

# Run rsync using the common function with delete mode
run_rsync "$SOURCE" "$DEST" "$DRY_RUN" "$EXCLUSIONS" "delete" ""