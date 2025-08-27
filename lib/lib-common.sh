#!/bin/bash
# Library - Common utilities for all scripts
# Not executable directly - source this file from other scripts

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
        echo "Copy .env.example to .env.local and configure your paths"
        return 1
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