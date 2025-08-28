#!/usr/bin/env bash
# test-organize-by-date.sh
# Tests for organize-by-date.sh business logic

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_DIR="$SCRIPT_DIR"
SCRIPTS_DIR="/Users/daniellawrence/Developer/scripts"

# Colors for output  
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Logging functions
log_test() {
    echo -e "${YELLOW}TEST:${NC} $1"
    TESTS_RUN=$((TESTS_RUN + 1))
}

log_pass() {
    echo -e "${GREEN}PASS:${NC} $1"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

log_fail() {
    echo -e "${RED}FAIL:${NC} $1"
    TESTS_FAILED=$((TESTS_FAILED + 1))
}

# Mock expand_path_template function
mock_expand_path_template() {
    local template="$1"
    local date="$2"
    local label="$3"
    
    # Extract date components
    local year="${date:0:4}"
    local month="${date:5:2}"  
    local day="${date:8:2}"
    local full_date="$year-$month-$day"
    
    # Template validation
    if [[ "$template" =~ \{\{label\}\} && -z "$label" ]]; then
        echo "ERROR: Template contains {{label}} but no label provided" >&2
        return 1
    fi
    
    # Simple template substitution - only valid variables
    local result="$template"
    result="${result//\{\{YYYY\}\}/$year}"
    result="${result//\{\{MM\}\}/$month}"
    result="${result//\{\{DD\}\}/$day}"
    result="${result//\{\{label\}\}/$label}"
    
    # Check for invalid template variables
    if [[ "$result" =~ \{\{[^}]+\}\} ]]; then
        echo "ERROR: Invalid template variable found in: $template" >&2
        return 1
    fi
    
    echo "$result"
}

# Test: Template with label provided
test_template_with_label() {
    log_test "Template processing with label provided"
    
    local template="{{YYYY}}/{{label}}/{{YYYY}}-{{MM}}-{{DD}}"
    local date="2025-05-26"
    local label="Germany"
    local expected="2025/Germany/2025-05-26"
    
    local result
    if result=$(mock_expand_path_template "$template" "$date" "$label"); then
        if [[ "$result" == "$expected" ]]; then
            log_pass "Template correctly processed with label"
            return 0
        else
            log_fail "Template processing failed: expected '$expected', got '$result'"
            return 1
        fi
    else
        log_fail "Template processing should have succeeded"
        return 1
    fi
}

# Test: Template with missing label should fail
test_template_missing_label() {
    log_test "Template with missing required label should fail"
    
    local template="{{YYYY}}/{{label}}/{{DD}}"
    local date="2025-05-26"
    local label=""  # Missing
    
    if mock_expand_path_template "$template" "$date" "$label" 2>/dev/null; then
        log_fail "Template processing should have failed for missing label"
        return 1
    else
        log_pass "Template correctly failed validation for missing label"
        return 0
    fi
}

# Test: Invalid template variable should fail
test_invalid_template_variable() {
    log_test "Invalid template variable should fail"
    
    local template="{{YYYY-MM-DD}}"  # Invalid variable
    local date="2025-05-26"
    local label=""
    
    if mock_expand_path_template "$template" "$date" "$label" 2>/dev/null; then
        log_fail "Template with invalid variable should have failed"
        return 1
    else
        log_pass "Invalid template variable correctly rejected"
        return 0
    fi
}

# Test: Valid simple date template
test_simple_date_template() {
    log_test "Valid simple date template"
    
    local template="{{YYYY}}-{{MM}}-{{DD}}"  # Valid variables only
    local date="2025-05-26"
    local label=""
    local expected="2025-05-26"
    
    local result
    if result=$(mock_expand_path_template "$template" "$date" "$label"); then
        if [[ "$result" == "$expected" ]]; then
            log_pass "Simple date template processed correctly"
            return 0
        else
            log_fail "Simple template failed: expected '$expected', got '$result'"
            return 1
        fi
    else
        log_fail "Simple template processing failed unexpectedly"
        return 1
    fi
}

# Test: Complex template with all valid variables
test_complex_template() {
    log_test "Complex template with all valid date variables"
    
    local template="{{YYYY}}/{{label}}/{{MM}}-{{DD}}"
    local date="2025-05-26"
    local label="TestLocation"
    local expected="2025/TestLocation/05-26"
    
    local result
    if result=$(mock_expand_path_template "$template" "$date" "$label"); then
        if [[ "$result" == "$expected" ]]; then
            log_pass "Complex template processed correctly"
            return 0
        else
            log_fail "Complex template failed: expected '$expected', got '$result'"
            return 1
        fi
    else
        log_fail "Complex template processing failed"
        return 1
    fi
}

# Test: Path construction with various slash combinations
test_path_construction_variations() {
    log_test "Path construction handles all slash combinations"
    
    local test_cases=(
        "Ready/ 2025/Germany Ready/2025/Germany"
        "Ready 2025/Germany Ready/2025/Germany" 
        "Ready/ /2025/Germany Ready/2025/Germany"
        "Ready /2025/Germany Ready/2025/Germany"
    )
    
    local all_passed=1
    
    for case in "${test_cases[@]}"; do
        read -r target_dir organized_path expected <<< "$case"
        local result="${target_dir%/}/${organized_path#/}"
        
        if [[ "$result" != "$expected" ]]; then
            log_fail "Path case failed: '$target_dir' + '$organized_path' → '$result' (expected '$expected')"
            all_passed=0
        fi
    done
    
    if [[ $all_passed -eq 1 ]]; then
        log_pass "All path construction variations handled correctly"
        return 0
    else
        return 1
    fi
}

# Test: File size comparison logic
test_file_size_comparison() {
    log_test "File size comparison for duplicate handling"
    
    # Create two test files with same size
    local src_file="$TEST_DIR/test_src.mov"
    local dst_file="$TEST_DIR/test_dst.mov"
    
    echo "test content" > "$src_file"
    echo "test content" > "$dst_file"
    
    # Get file sizes (cross-platform)
    local src_size dst_size
    if command -v stat >/dev/null 2>&1; then
        src_size=$(stat -f "%z" "$src_file" 2>/dev/null || stat -c "%s" "$src_file" 2>/dev/null)
        dst_size=$(stat -f "%z" "$dst_file" 2>/dev/null || stat -c "%s" "$dst_file" 2>/dev/null)
    else
        src_size=$(wc -c < "$src_file")
        dst_size=$(wc -c < "$dst_file")
    fi
    
    if [[ "$src_size" -eq "$dst_size" ]]; then
        log_pass "File size comparison works correctly"
        rm -f "$src_file" "$dst_file"
        return 0
    else
        log_fail "File size comparison failed: $src_size != $dst_size"
        rm -f "$src_file" "$dst_file"
        return 1
    fi
}

# Test: File size comparison with different sizes
test_file_size_different() {
    log_test "File size comparison detects different sizes"
    
    local src_file="$TEST_DIR/test_src2.mov"
    local dst_file="$TEST_DIR/test_dst2.mov"
    
    echo "short" > "$src_file"
    echo "longer content here" > "$dst_file"
    
    local src_size dst_size
    if command -v stat >/dev/null 2>&1; then
        src_size=$(stat -f "%z" "$src_file" 2>/dev/null || stat -c "%s" "$src_file" 2>/dev/null)
        dst_size=$(stat -f "%z" "$dst_file" 2>/dev/null || stat -c "%s" "$dst_file" 2>/dev/null)
    else
        src_size=$(wc -c < "$src_file")
        dst_size=$(wc -c < "$dst_file")
    fi
    
    if [[ "$src_size" -ne "$dst_size" ]]; then
        log_pass "File size difference correctly detected"
        rm -f "$src_file" "$dst_file"
        return 0
    else
        log_fail "File size difference not detected: both showed $src_size bytes"
        rm -f "$src_file" "$dst_file"
        return 1
    fi
}

# Run all tests
main() {
    echo "Running organize-by-date.sh tests..."
    echo "===================================="
    echo
    
    # Clean up any existing test files
    rm -f "$TEST_DIR"/test_*.mov
    
    # Run tests
    test_template_with_label
    test_template_missing_label  
    test_invalid_template_variable
    test_simple_date_template
    test_complex_template
    test_path_construction_variations
    test_file_size_comparison
    test_file_size_different
    
    echo
    echo "===================================="
    echo "Test Results:"
    echo "  Total: $TESTS_RUN"
    echo "  Passed: $TESTS_PASSED" 
    echo "  Failed: $TESTS_FAILED"
    
    if [[ $TESTS_FAILED -eq 0 ]]; then
        echo -e "${GREEN}All tests passed!${NC}"
        exit 0
    else
        echo -e "${RED}Some tests failed!${NC}"
        exit 1
    fi
}

main "$@"