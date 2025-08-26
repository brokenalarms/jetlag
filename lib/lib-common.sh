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

# Get script directory - common pattern across all scripts
# Usage: SCRIPT_DIR="$(get_script_dir)"
get_script_dir() {
    echo "$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
}

# Validate file exists with error message
# Usage: validate_file_exists "path/to/file" || exit 1
validate_file_exists() {
    local file_path="$1"
    if [[ ! -f "$file_path" ]]; then
        echo "ERROR: File not found: $file_path" >&2
        return 1
    fi
}

# Validate directory exists with error message
# Usage: validate_dir_exists "path/to/dir" || exit 1
validate_dir_exists() {
    local dir_path="$1"
    if [[ ! -d "$dir_path" ]]; then
        echo "ERROR: Directory not found: $dir_path" >&2
        return 1
    fi
}

# Compare file sizes (cross-platform)
# Usage: compare_file_sizes "file1" "file2" && echo "same size"
compare_file_sizes() {
    local file1="$1"
    local file2="$2"
    local size1 size2
    
    # Get file sizes (macOS/Linux compatible)
    size1=$(stat -f "%z" "$file1" 2>/dev/null || stat -c "%s" "$file1" 2>/dev/null)
    size2=$(stat -f "%z" "$file2" 2>/dev/null || stat -c "%s" "$file2" 2>/dev/null)
    
    [[ "$size1" == "$size2" ]]
}

# Show standard help pattern
# Usage: show_standard_help "script-name" "description" "additional_options"
show_standard_help() {
    local script_name="$1"
    local description="$2"
    local additional_options="${3:-}"
    
    echo "Usage: $script_name [OPTIONS]"
    echo ""
    echo "$description"
    echo ""
    echo "Standard Options:"
    echo "  --apply         Apply changes (default: dry run)"
    echo "  --verbose, -v   Show detailed processing info"
    echo "  --help, -h      Show this help"
    if [[ -n "$additional_options" ]]; then
        echo ""
        echo "Additional Options:"
        echo "$additional_options"
    fi
    echo ""
    echo "Without --apply, this script will show you what changes would be made"
    echo "without actually performing them."
}

# Parse common arguments (--apply, --verbose, --help)
# Usage: parse_common_args "$@" || { echo "Unknown option"; exit 1; }
# Sets global variables: APPLY, VERBOSE
parse_common_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --apply)
                APPLY=1
                DRY_RUN=0
                shift
                ;;
            --verbose|-v)
                VERBOSE=1
                shift
                ;;
            --help|-h)
                return 2  # Special return code to indicate help was requested
                ;;
            *)
                # Unknown argument - let caller handle it
                return 1
                ;;
        esac
    done
    
    # Set defaults if not set
    APPLY=${APPLY:-0}
    DRY_RUN=${DRY_RUN:-1}
    VERBOSE=${VERBOSE:-0}
    
    export APPLY DRY_RUN VERBOSE
    return 0
}