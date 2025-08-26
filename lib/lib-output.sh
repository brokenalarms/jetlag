#!/bin/bash
# Library - Common output/printing functions for consistent formatting
# Not executable directly - source this file from other scripts

# Print success message with green checkmark
# Usage: print_success "message"
print_success() {
    echo "✅ $1"
}

# Print error message to stderr with red cross
# Usage: print_error "message"
print_error() {
    echo "❌ $1" >&2
}

# Print warning message with yellow warning sign
# Usage: print_warning "message"
print_warning() {
    echo "⚠️ $1"
}

# Print info message with blue info icon
# Usage: print_info "message"
print_info() {
    echo "ℹ️ $1"
}

# Print progress indicator
# Usage: print_progress current total "message"
print_progress() {
    local current="$1"
    local total="$2"
    local message="$3"
    echo "[$current/$total] $message"
}

# Print mode status (DRY RUN vs APPLY)
# Usage: print_mode_status $apply_flag
print_mode_status() {
    local apply_flag="$1"
    if [[ $apply_flag -eq 1 ]]; then
        echo "💾 Mode: APPLY"
    else
        echo "🧪 Mode: DRY RUN (no changes)"
    fi
}

# Print section header with separator
# Usage: print_section "Section Name"
print_section() {
    echo ""
    echo "=========================================="
    echo "📋 $1"
    echo "----------------------------------------"
}

# Print file operation status
# Usage: print_file_op "action" "source" "destination"
print_file_op() {
    local action="$1"
    local source="$2" 
    local destination="$3"
    echo "📄 $action: $source → $destination"
}

# Print sync status
# Usage: print_sync_status "message"
print_sync_status() {
    echo "🔄 $1"
}

# Print completion summary
# Usage: print_completion_summary $processed $total $failed
print_completion_summary() {
    local processed="$1"
    local total="$2"
    local failed="${3:-0}"
    
    echo ""
    echo "=========================================="
    echo "📊 PROCESSING SUMMARY"
    echo "----------------------------------------"
    echo "Total files: $total"
    echo "Processed: $processed"
    if [[ $failed -gt 0 ]]; then
        echo "Failed: $failed"
    fi
}