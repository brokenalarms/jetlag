#!/bin/bash
# Library - Sync/rsync functionality for backup scripts
# Not executable directly - source this file from other scripts

# Output conventions:
# - Human-readable messages go to stderr
# - Machine-readable data goes to stdout with @@ prefix:
#   @@files_transferred=N
#   @@bytes_transferred=N
#   @@total_size=N

# Function to run rsync with standard options
# Usage: run_rsync SOURCE DEST DRY_RUN [EXCLUSIONS_FILE] [DELETE_FLAG] [EXTRA_EXCLUDES] [EXTRA_ARGS] [MACHINE_READABLE]
# DELETE_FLAG: "" (default - no delete), "delete", or custom delete flags
# EXTRA_EXCLUDES: Additional exclude patterns (separate from exclusions file)
# MACHINE_READABLE: "1" to emit @@key=value lines to stdout for parent script parsing
run_rsync() {
    local SOURCE="$1"
    local DEST="$2"
    local DRY_RUN="$3"
    local EXCLUSIONS="${4:-}"
    local DELETE_FLAG="${5:-}"
    local EXTRA_EXCLUDES="${6:-}"
    local EXTRA_ARGS="${7:-}"
    local MACHINE_READABLE="${8:-0}"
    
    # Build rsync command
    # Note: Removed -z (rsync compression) to avoid "deflate on token" errors with large files
    # We use SSH compression (-C) instead which is more reliable
    local RSYNC_ARGS="-avi --no-perms --no-owner --no-group --no-links --omit-dir-times --human-readable"

    # Add bandwidth limit for remote transfers only (if RSYNC_BW_LIMIT is set)
    # Only applies to network/SSH copies, not local disk-to-disk transfers
    # Set in .env.local: RSYNC_BW_LIMIT=5000  (KB/s, ~5 MB/s is typically safe)
    if [[ "$DEST" == *"@"* ]] && [[ -n "${RSYNC_BW_LIMIT:-}" ]] && [[ "${RSYNC_BW_LIMIT}" != "0" ]]; then
        RSYNC_ARGS="$RSYNC_ARGS --bwlimit=${RSYNC_BW_LIMIT}"
    fi
    
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
    # Always include --stats for machine-readable output
    RSYNC_ARGS="$RSYNC_ARGS --stats"
    if [[ $DRY_RUN -eq 1 ]]; then
        RSYNC_ARGS="$RSYNC_ARGS --dry-run --info=name"
    else
        # Per-file progress display
        RSYNC_ARGS="$RSYNC_ARGS --progress"
    fi
    
    # Add any extra arguments
    if [[ -n "$EXTRA_ARGS" ]]; then
        RSYNC_ARGS="$RSYNC_ARGS $EXTRA_ARGS"
    fi
    
    # Run rsync (human-readable to stderr, machine-readable @@ to stdout)
    echo "🔄 Starting sync..." >&2
    if [[ $DRY_RUN -eq 1 ]]; then
        echo "(This is a dry run - no files will be copied)" >&2
        echo "" >&2
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

    # Capture output to parse stats
    local RSYNC_OUTPUT
    local RSYNC_EXIT_CODE

    # Capture output while displaying
    # No grep in pipeline - avoids buffering that breaks --progress display
    local RSYNC_TEMP
    RSYNC_TEMP=$(mktemp)
    local INTERRUPTED=0
    local START_TIME
    START_TIME=$(date +%s)

    # Trap to handle Ctrl+C - set flag to parse partial stats before exit
    trap 'INTERRUPTED=1' INT

    # Stream separation:
    # - rsync stdout → tee (capture to file + display to stderr)
    # - rsync stderr → grep filter (remove "skipping" messages) → stderr
    local RSYNC_EXIT_FILE
    RSYNC_EXIT_FILE=$(mktemp)
    ( $RSYNC_CMD -e "ssh -C" $RSYNC_ARGS "${EXCLUDE_ARGS[@]}" "$SOURCE" "$DEST" \
        2> >(grep --line-buffered -v "skipping non-regular file" >&2) \
        > >(tee "$RSYNC_TEMP" >&2); echo $? > "$RSYNC_EXIT_FILE" )
    RSYNC_EXIT_CODE=$(cat "$RSYNC_EXIT_FILE")
    rm -f "$RSYNC_EXIT_FILE"

    local END_TIME
    END_TIME=$(date +%s)
    local ELAPSED=$((END_TIME - START_TIME))

    # Remove trap
    trap - INT

    # Read captured stdout for stats parsing (stderr filtered separately above)
    RSYNC_OUTPUT=$(cat "$RSYNC_TEMP" 2>/dev/null || true)
    rm -f "$RSYNC_TEMP"

    # If interrupted, we still continue to parse stats below, then exit

    # Clean up password from environment
    unset SSHPASS
    set -e

    # Parse stats from rsync output and emit @@ lines to stdout
    local files_transferred=0
    local bytes_transferred=0
    local total_size=0

    # Helper function to convert human-readable size to bytes
    # Handles formats like "108.12G", "1.56T", "500M", "1234" (plain bytes)
    convert_to_bytes() {
        local size_str="$1"
        local num unit multiplier=1

        if [[ "$size_str" =~ ^([0-9.,]+)([KMGT]?)$ ]]; then
            num="${BASH_REMATCH[1]//,/}"
            unit="${BASH_REMATCH[2]}"
            case "$unit" in
                K) multiplier=1024 ;;
                M) multiplier=1048576 ;;
                G) multiplier=1073741824 ;;
                T) multiplier=1099511627776 ;;
            esac
            awk "BEGIN {printf \"%.0f\", $num * $multiplier}"
        else
            echo "0"
        fi
    }

    # Try to parse from --stats output first (only present if rsync completed)
    # rsync with --human-readable outputs "Total transferred file size: 108.12G bytes"
    if [[ "$RSYNC_OUTPUT" =~ Number\ of\ regular\ files\ transferred:\ ([0-9,]+) ]]; then
        files_transferred="${BASH_REMATCH[1]//,/}"
    fi

    if [[ "$RSYNC_OUTPUT" =~ Total\ transferred\ file\ size:\ ([0-9.,]+[KMGT]?)\ bytes ]]; then
        bytes_transferred=$(convert_to_bytes "${BASH_REMATCH[1]}")
    fi

    if [[ "$RSYNC_OUTPUT" =~ Total\ file\ size:\ ([0-9.,]+[KMGT]?)\ bytes ]]; then
        total_size=$(convert_to_bytes "${BASH_REMATCH[1]}")
    fi

    # If no stats (interrupted), parse from progress output for completed files
    # Progress lines look like: "272.51M 100%  5.52MB/s  0:00:47 (xfr#1, ...)"
    if [[ "$files_transferred" -eq 0 ]] && [[ "$RSYNC_OUTPUT" == *"100%"* ]]; then
        # Count files that reached 100%
        files_transferred=$(echo "$RSYNC_OUTPUT" | grep -c "100%" || true)

        # Sum up bytes from completed files
        # Format: "272.51M 100%" or "1.23G 100%" etc
        local size_sum=0
        while IFS= read -r line; do
            if [[ "$line" =~ ([0-9.]+)([KMGT]?)\ +100% ]]; then
                local num="${BASH_REMATCH[1]}"
                local unit="${BASH_REMATCH[2]}"
                local multiplier=1
                case "$unit" in
                    K) multiplier=1024 ;;
                    M) multiplier=1048576 ;;
                    G) multiplier=1073741824 ;;
                    T) multiplier=1099511627776 ;;
                esac
                # Use awk for floating point math
                local bytes=$(awk "BEGIN {printf \"%.0f\", $num * $multiplier}")
                size_sum=$((size_sum + bytes))
            fi
        done <<< "$RSYNC_OUTPUT"
        bytes_transferred=$size_sum
    fi

    # Output machine-readable data to stdout (only if requested by parent)
    if [[ "$MACHINE_READABLE" == "1" ]]; then
        echo "@@files_transferred=$files_transferred"
        echo "@@bytes_transferred=$bytes_transferred"
        echo "@@total_size=$total_size"
        echo "@@elapsed_seconds=$ELAPSED"
    fi

    echo "" >&2
    if [[ $RSYNC_EXIT_CODE -eq 0 ]]; then
        if [[ $DRY_RUN -eq 1 ]]; then
            if [[ "$files_transferred" -eq 0 ]]; then
                echo "✅ Everything is up to date - no files need to be synced" >&2
            else
                echo "📝 Files that would be synced are listed above" >&2
            fi
            echo "🧪 Dry run completed. Use --apply to perform the actual sync." >&2
        else
            echo "✅ Sync completed successfully" >&2
        fi
    else
        echo "❌ Sync failed with error code: $RSYNC_EXIT_CODE" >&2
        echo "Common error codes: 12=Protocol error, 23=Partial transfer, 24=Files vanished" >&2
        return $RSYNC_EXIT_CODE
    fi
}

