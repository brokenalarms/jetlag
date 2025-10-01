#!/bin/bash
set -euo pipefail

# Get script directory for loading environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source common libraries
source "$SCRIPT_DIR/lib/lib-common.sh"
source "$SCRIPT_DIR/lib/lib-sync.sh"

# Function to show help
show_help() {
    echo "Usage: insta360-sync-to-nas.sh [OPTIONS]"
    echo "Sync Insta360 raw footage to NAS using paths configured in .env.local"
    echo ""
    echo "Options:"
    echo "  --apply         Actually perform the sync (default: dry run)"
    echo "  --help, -h      Show this help"
    echo ""
    echo "Configuration:"
    echo "  Sync paths are configured in .env.local:"
    echo "    INSTA360_IMPORT_FOLDER     - Local Insta360 raw folder"
    echo "    NAS_INSTA360_IMPORT_FOLDER - NAS destination folder"
    echo "    NAS_USER                - NAS username"
    echo "    NAS_HOST                - NAS hostname"
    echo "    EXCLUSIONS_FILE         - File containing rsync exclusions (optional)"
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
if [[ -z "${INSTA360_IMPORT_FOLDER:-}" || -z "${NAS_INSTA360_IMPORT_FOLDER:-}" || -z "${NAS_USER:-}" || -z "${NAS_HOST:-}" ]]; then
    echo "ERROR: Missing required environment variables"
    echo "Required: INSTA360_IMPORT_FOLDER, NAS_INSTA360_IMPORT_FOLDER, NAS_USER, NAS_HOST"
    echo "Check your .env.local file"
    exit 1
fi

# Set paths from environment
SOURCE="$INSTA360_IMPORT_FOLDER"
DEST="${NAS_USER}@${NAS_HOST}:${NAS_INSTA360_IMPORT_FOLDER}"
EXCLUSIONS="${EXCLUSIONS_FILE:-${HOME}/.exclusions.txt}"

# Validate source path exists
if [[ ! -d "$SOURCE" ]]; then
    echo "ERROR: Source folder not found: $SOURCE" >&2
    exit 1
fi

echo "📹 Insta360 to NAS Sync"
echo "Source:      $SOURCE"
echo "Destination: $DEST"
echo "Exclusions:  $EXCLUSIONS"

if [[ $DRY_RUN -eq 1 ]]; then
    echo "Mode:        DRY RUN (no changes will be made)"
    echo "Use --apply to perform actual sync"
else
    echo "Mode:        APPLYING CHANGES"
fi

echo ""

# Run rsync using the common function with delete mode
run_rsync "$SOURCE" "$DEST" "$DRY_RUN" "$EXCLUSIONS" "delete" ""