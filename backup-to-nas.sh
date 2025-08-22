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

echo "🔄 Starting backup to NAS..."
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

# Run rsync with environment variables
rsync -avz --delete --no-perms --no-owner --no-group --no-links --omit-dir-times --progress --stats $EXCLUDE_ARG "$SOURCE_PATH" "$NAS_USER@$NAS_HOST:$NAS_BACKUP_PATH"

echo "✅ Backup completed successfully"
