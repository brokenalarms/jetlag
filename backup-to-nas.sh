#!/bin/bash
set -euo pipefail

# Get script directory for loading environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source common libraries
source "$SCRIPT_DIR/lib/lib-common.sh"
source "$SCRIPT_DIR/lib/lib-sync.sh"

# Function to show usage
show_usage() {
    echo "Usage: $0 [--apply] [--source PATH] [--dest PATH] [--exclude PATTERNS]"
    echo ""
    echo "Options:"
    echo "  --apply              Actually perform the backup (dry-run by default)"
    echo "  --source PATH        Override SOURCE_PATH from environment"
    echo "  --dest PATH          Override NAS_BACKUP_PATH from environment"
    echo "  --exclude PATTERNS   Pipe-separated exclusion patterns (e.g. 'Dir1/|Dir2/')"
    echo "  --help               Show this help message"
    echo ""
    echo "Without --apply, this script will show you what changes would be made"
    echo "without actually performing the backup."
}

# Parse command line arguments
OVERRIDE_SOURCE=""
OVERRIDE_DEST=""
ADDITIONAL_EXCLUDE=""
EXTRA_RSYNC_ARGS=()
while [[ $# -gt 0 ]]; do
    case $1 in
        --apply)
            DRY_RUN=0
            shift
            ;;
        --source)
            OVERRIDE_SOURCE="$2"
            shift 2
            ;;
        --dest)
            OVERRIDE_DEST="$2"
            shift 2
            ;;
        --exclude)
            ADDITIONAL_EXCLUDE="$2"
            shift 2
            ;;
        --help|-h)
            show_usage
            exit 0
            ;;
        *)
            # Pass unknown arguments through to rsync
            EXTRA_RSYNC_ARGS+=("$1")
            shift
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

# Set paths from environment (allow overrides from command line)
SOURCE="${OVERRIDE_SOURCE:-$SOURCE_PATH}"
NAS_BACKUP_PATH="${OVERRIDE_DEST:-$NAS_BACKUP_PATH}"
DEST="${NAS_USER}@${NAS_HOST}:${NAS_BACKUP_PATH}"
EXCLUSIONS="${EXCLUSIONS_FILE:-${HOME}/.exclusions.txt}"

# Validate source path exists
if [[ ! -d "$SOURCE" ]]; then
    echo "ERROR: Source folder not found: $SOURCE" >&2
    exit 1
fi

if [[ "$DRY_RUN" -eq 0 ]]; then
    echo "🔄 Starting backup to NAS..." >&2
else
    echo "🔍 DRY RUN: Showing what would be backed up to NAS..." >&2
    echo "Use --apply to actually perform the backup" >&2
fi
echo "Source: $SOURCE" >&2
echo "Destination: $DEST" >&2
echo "Exclusions: $EXCLUSIONS" >&2
if [[ -n "$ADDITIONAL_EXCLUDE" ]]; then
    echo "Additional exclusions: $ADDITIONAL_EXCLUDE" >&2
fi
echo >&2

# Run rsync using the common function
# No delete by default (incremental backup)
# Additional exclude patterns from command line or empty string
run_rsync "$SOURCE" "$DEST" "$DRY_RUN" "$EXCLUSIONS" "" "$ADDITIONAL_EXCLUDE" "${EXTRA_RSYNC_ARGS[*]:-}"