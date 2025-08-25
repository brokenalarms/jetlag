#!/bin/bash
# Common rsync functionality for backup scripts

# Function to run rsync with standard options
# Usage: run_rsync SOURCE DEST DRY_RUN [EXCLUSIONS_FILE] [DELETE_FLAG] [EXTRA_EXCLUDES] [EXTRA_ARGS]
# DELETE_FLAG: "" (default - no delete), "delete", or custom delete flags
# EXTRA_EXCLUDES: Additional exclude patterns (separate from exclusions file)
run_rsync() {
    local SOURCE="$1"
    local DEST="$2"
    local DRY_RUN="$3"
    local EXCLUSIONS="${4:-}"
    local DELETE_FLAG="${5:-}"
    local EXTRA_EXCLUDES="${6:-}"
    local EXTRA_ARGS="${7:-}"
    
    # Build rsync command (no compression by default - can be added via EXTRA_ARGS if needed)
    local RSYNC_ARGS="-av --partial --no-perms --no-owner --no-group --no-links --omit-dir-times --size-only --human-readable"
    
    # Add delete options if requested
    if [[ "$DELETE_FLAG" == "delete" ]]; then
        RSYNC_ARGS="$RSYNC_ARGS --delete-during --force-delete --ignore-errors"
    elif [[ -n "$DELETE_FLAG" ]]; then
        # Custom delete flags provided
        RSYNC_ARGS="$RSYNC_ARGS $DELETE_FLAG"
    fi
    
    # Build exclusion arguments array
    local EXCLUDE_ARGS=()
    if [[ -n "$EXCLUSIONS" && -f "$EXCLUSIONS" ]]; then
        EXCLUDE_ARGS+=("--exclude-from=$EXCLUSIONS")
    elif [[ -n "$EXCLUSIONS" ]]; then
        echo "⚠️  Exclusions file not found: $EXCLUSIONS"
        echo "Continuing without exclusions..."
    fi
    
    # Add extra exclude patterns if provided
    if [[ -n "$EXTRA_EXCLUDES" ]]; then
        # EXTRA_EXCLUDES can contain multiple patterns separated by |
        IFS='|' read -ra EXCLUDES_ARRAY <<< "$EXTRA_EXCLUDES"
        for pattern in "${EXCLUDES_ARRAY[@]}"; do
            EXCLUDE_ARGS+=("--exclude=$pattern")
        done
    fi
    
    # Add dry run flag and adjust output format
    if [[ $DRY_RUN -eq 1 ]]; then
        RSYNC_ARGS="$RSYNC_ARGS --dry-run --info=name,stats2"
    else
        # Show per-file progress with --progress flag
        RSYNC_ARGS="$RSYNC_ARGS --progress"
    fi
    
    # Add any extra arguments
    if [[ -n "$EXTRA_ARGS" ]]; then
        RSYNC_ARGS="$RSYNC_ARGS $EXTRA_ARGS"
    fi
    
    # Run rsync
    echo "🔄 Starting sync..."
    if [[ $DRY_RUN -eq 1 ]]; then
        echo "(This is a dry run - no files will be copied)"
        echo ""
    fi
    
    # Capture rsync exit code
    set +e
    
    # Check if we should use sshpass for password authentication
    local RSYNC_CMD="rsync"
    if [[ -n "${NAS_PASSWORD:-}" ]] && [[ "$DEST" == *"@"* ]]; then
        # Use sshpass for remote destinations when password is provided
        RSYNC_CMD="sshpass -e rsync"
        export SSHPASS="$NAS_PASSWORD"
    fi
    
    if [[ $DRY_RUN -eq 1 ]]; then
        # Filter output during dry run and capture for analysis
        local RSYNC_OUTPUT
        RSYNC_OUTPUT=$($RSYNC_CMD $RSYNC_ARGS "${EXCLUDE_ARGS[@]}" "$SOURCE" "$DEST" 2>&1 | grep -v "skipping non-regular file" | tee /dev/tty)
        local RSYNC_EXIT_CODE="${PIPESTATUS[0]}"
    else
        # No filtering during actual transfer to preserve progress updates
        $RSYNC_CMD $RSYNC_ARGS "${EXCLUDE_ARGS[@]}" "$SOURCE" "$DEST"
        local RSYNC_EXIT_CODE=$?
    fi
    
    # Clean up password from environment
    unset SSHPASS
    set -e
    
    echo ""
    if [[ $RSYNC_EXIT_CODE -eq 0 ]]; then
        if [[ $DRY_RUN -eq 1 ]]; then
            # Check if any files would be transferred
            if [[ "$RSYNC_OUTPUT" == *"Number of regular files transferred: 0"* ]]; then
                echo "✅ Everything is up to date - no files need to be synced"
            else
                echo "📝 Files that would be synced are listed above"
            fi
            echo "🧪 Dry run completed. Use --apply to perform the actual sync."
        else
            echo "✅ Sync completed successfully"
        fi
    else
        echo "❌ Sync failed with error code: $RSYNC_EXIT_CODE"
        echo "Common error codes: 12=Protocol error, 23=Partial transfer, 24=Files vanished"
        return $RSYNC_EXIT_CODE
    fi
}

# Function to validate paths exist
# Usage: validate_paths SOURCE DEST
validate_paths() {
    local SOURCE="$1"
    local DEST_PATH="$2"
    
    # Check source
    if [[ ! -d "$SOURCE" ]]; then
        echo "ERROR: Source not found: $SOURCE" >&2
        return 1
    fi
    
    # For remote destinations, just check if we can parse it
    if [[ "$DEST_PATH" == *":"* ]]; then
        # Remote destination - basic validation only
        if [[ -z "$DEST_PATH" ]]; then
            echo "ERROR: Empty destination path" >&2
            return 1
        fi
    else
        # Local destination - check if directory exists
        if [[ ! -d "$DEST_PATH" ]]; then
            echo "ERROR: Destination not found: $DEST_PATH" >&2
            return 1
        fi
    fi
    
    return 0
}

# Function to load environment from .env.local
# Usage: load_env SCRIPT_DIR
load_env() {
    local SCRIPT_DIR="$1"
    
    if [[ -f "$SCRIPT_DIR/.env.local" ]]; then
        # Source the file directly (bash will ignore comments)
        set -a  # Export all variables
        source "$SCRIPT_DIR/.env.local"
        set +a  # Stop exporting
    else
        echo "ERROR: .env.local not found"
        echo "Copy .env.example to .env.local and configure your backup paths"
        return 1
    fi
}

# Function to parse standard arguments
# Sets DRY_RUN variable (0 or 1)
# Usage: parse_args "$@"
parse_args() {
    DRY_RUN=1  # Default to dry run
    
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --apply) 
                DRY_RUN=0
                shift ;;
            *)
                # Unknown argument - let caller handle it
                return 1 ;;
        esac
    done
    
    export DRY_RUN
    return 0
}