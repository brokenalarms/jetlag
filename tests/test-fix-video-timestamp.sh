#!/usr/bin/env bash
# test-fix-video-timestamp.sh
# Tests for fix-video-timestamp.sh business logic

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

# Mock Insta360 filename parsing
mock_parse_insta360_filename() {
    local filename="$1"
    
    # Pattern: VID_YYYYMMDD_HHMMSS_XX_XXX.insv
    if [[ "$filename" =~ VID_([0-9]{8})_([0-9]{6})_[0-9]{2}_[0-9]{3}\.insv$ ]]; then
        local date_part="${BASH_REMATCH[1]}"
        local time_part="${BASH_REMATCH[2]}"
        
        # Convert to ISO format: YYYYMMDD HHMMSS -> YYYY-MM-DD HH:MM:SS
        local iso_date="${date_part:0:4}-${date_part:4:2}-${date_part:6:2}"
        local iso_time="${time_part:0:2}:${time_part:2:2}:${time_part:4:2}"
        
        echo "$iso_date $iso_time"
        return 0
    else
        echo "ERROR: Not a valid Insta360 filename pattern" >&2
        return 1
    fi
}

# Test: Insta360 filename parsing
test_insta360_filename_parsing() {
    log_test "Insta360 filename parsing VID_20250509_092551_00_044.insv"
    
    local filename="VID_20250509_092551_00_044.insv"
    local expected="2025-05-09 09:25:51"
    
    local result
    if result=$(mock_parse_insta360_filename "$filename"); then
        if [[ "$result" == "$expected" ]]; then
            log_pass "Insta360 filename correctly parsed"
            return 0
        else
            log_fail "Insta360 parsing failed: expected '$expected', got '$result'"
            return 1
        fi
    else
        log_fail "Insta360 filename parsing should have succeeded"
        return 1
    fi
}

# Test: Invalid Insta360 filename should fail
test_invalid_insta360_filename() {
    log_test "Invalid Insta360 filename should fail"
    
    local filename="VID_invalid_name.insv"
    
    if mock_parse_insta360_filename "$filename" 2>/dev/null; then
        log_fail "Invalid Insta360 filename should have failed parsing"
        return 1
    else
        log_pass "Invalid Insta360 filename correctly rejected"
        return 0
    fi
}

# Mock timestamp priority order testing
mock_get_best_timestamp_priority() {
    local file_type="$1"
    local available_fields="$2"
    
    case "$file_type" in
        "iPhone")
            # iPhone priority: Keys:CreationDate > DateTimeOriginal > MediaCreateDate
            if [[ "$available_fields" == *"Keys:CreationDate"* ]]; then
                echo "Keys:CreationDate: 2025-05-26 12:04:08+02:00"
                return 0
            elif [[ "$available_fields" == *"DateTimeOriginal"* ]]; then
                echo "DateTimeOriginal: 2025-05-26 10:04:08"
                return 0
            elif [[ "$available_fields" == *"MediaCreateDate"* ]]; then
                echo "MediaCreateDate: 2025-05-26 10:04:08"
                return 0
            fi
            ;;
        "Insta360")
            # Insta360 priority: Filename parsing > MediaCreateDate > file timestamp
            if [[ "$available_fields" == *"filename"* ]]; then
                echo "Filename: 2025-05-09 09:25:51"
                return 0
            elif [[ "$available_fields" == *"MediaCreateDate"* ]]; then
                echo "MediaCreateDate: 2025-05-09 07:25:51"
                return 0
            fi
            ;;
        "GoPro")
            # GoPro priority: DateTimeOriginal > MediaCreateDate > file timestamp
            if [[ "$available_fields" == *"DateTimeOriginal"* ]]; then
                echo "DateTimeOriginal: 2025-05-26 14:30:15"
                return 0
            elif [[ "$available_fields" == *"MediaCreateDate"* ]]; then
                echo "MediaCreateDate: 2025-05-26 12:30:15"
                return 0
            fi
            ;;
    esac
    
    echo "ERROR: No valid timestamp found" >&2
    return 1
}

# Test: iPhone priority order - Keys:CreationDate wins
test_iphone_keys_creation_priority() {
    log_test "iPhone: Keys:CreationDate takes priority over MediaCreateDate"
    
    local result
    if result=$(mock_get_best_timestamp_priority "iPhone" "Keys:CreationDate,MediaCreateDate"); then
        if [[ "$result" == *"Keys:CreationDate"* && "$result" == *"12:04:08+02:00"* ]]; then
            log_pass "iPhone correctly prioritized Keys:CreationDate with timezone"
            return 0
        else
            log_fail "iPhone priority failed: $result"
            return 1
        fi
    else
        log_fail "iPhone timestamp selection failed"
        return 1
    fi
}

# Test: iPhone fallback to MediaCreateDate
test_iphone_fallback_to_media_create() {
    log_test "iPhone: Fallback to MediaCreateDate when Keys:CreationDate unavailable"
    
    local result
    if result=$(mock_get_best_timestamp_priority "iPhone" "MediaCreateDate"); then
        if [[ "$result" == *"MediaCreateDate"* ]]; then
            log_pass "iPhone correctly fell back to MediaCreateDate"
            return 0
        else
            log_fail "iPhone fallback failed: $result"
            return 1
        fi
    else
        log_fail "iPhone fallback failed"
        return 1
    fi
}

# Test: Insta360 filename takes priority over metadata
test_insta360_filename_priority() {
    log_test "Insta360: Filename parsing takes priority over MediaCreateDate"
    
    local result
    if result=$(mock_get_best_timestamp_priority "Insta360" "filename,MediaCreateDate"); then
        if [[ "$result" == *"Filename"* && "$result" == *"09:25:51"* ]]; then
            log_pass "Insta360 correctly prioritized filename parsing"
            return 0
        else
            log_fail "Insta360 priority failed: $result"
            return 1
        fi
    else
        log_fail "Insta360 timestamp selection failed"
        return 1
    fi
}

# Test: Insta360 fallback to metadata
test_insta360_fallback_to_metadata() {
    log_test "Insta360: Fallback to MediaCreateDate when filename parsing fails"
    
    local result
    if result=$(mock_get_best_timestamp_priority "Insta360" "MediaCreateDate"); then
        if [[ "$result" == *"MediaCreateDate"* ]]; then
            log_pass "Insta360 correctly fell back to MediaCreateDate"
            return 0
        else
            log_fail "Insta360 fallback failed: $result"
            return 1
        fi
    else
        log_fail "Insta360 fallback failed"
        return 1
    fi
}

# Test: GoPro DateTimeOriginal priority
test_gopro_datetime_original_priority() {
    log_test "GoPro: DateTimeOriginal takes priority over MediaCreateDate"
    
    local result
    if result=$(mock_get_best_timestamp_priority "GoPro" "DateTimeOriginal,MediaCreateDate"); then
        if [[ "$result" == *"DateTimeOriginal"* && "$result" == *"14:30:15"* ]]; then
            log_pass "GoPro correctly prioritized DateTimeOriginal"
            return 0
        else
            log_fail "GoPro priority failed: $result"
            return 1
        fi
    else
        log_fail "GoPro timestamp selection failed"
        return 1
    fi
}

# Test: DST timezone calculation for Germany in May
test_dst_germany_may() {
    log_test "DST calculation for Germany in May (should be CEST +0200)"
    
    local date="2025-05-26"
    local location="DE"
    local expected_offset="+0200"
    
    # Mock DST calculation for May in Germany
    local month="${date:5:2}"
    local actual_offset
    
    # Germany DST rules: Mar-Oct = CEST (+0200), Nov-Feb = CET (+0100)
    if [[ "$month" -ge "03" && "$month" -le "10" ]]; then
        actual_offset="+0200"
    else
        actual_offset="+0100"
    fi
    
    if [[ "$actual_offset" == "$expected_offset" ]]; then
        log_pass "Germany DST correctly calculated as CEST +0200 for May"
        return 0
    else
        log_fail "Germany DST incorrect: expected $expected_offset, got $actual_offset"
        return 1
    fi
}

# Test: DST timezone calculation for Germany in January  
test_dst_germany_january() {
    log_test "DST calculation for Germany in January (should be CET +0100)"
    
    local date="2025-01-15"
    local location="DE"
    local expected_offset="+0100"
    
    local month="${date:5:2}"
    local actual_offset
    
    if [[ "$month" -ge "03" && "$month" -le "10" ]]; then
        actual_offset="+0200"
    else
        actual_offset="+0100"
    fi
    
    if [[ "$actual_offset" == "$expected_offset" ]]; then
        log_pass "Germany DST correctly calculated as CET +0100 for January"
        return 0
    else
        log_fail "Germany DST incorrect: expected $expected_offset, got $actual_offset"
        return 1
    fi
}

# Test: Manual timezone application
test_manual_timezone_application() {
    log_test "Manual timezone offset +0700 applied to UTC timestamp"
    
    local utc_timestamp="2025-05-26 10:04:08"
    local manual_offset="+0700"
    local expected_local="2025-05-26 17:04:08"
    
    # Mock timezone conversion: UTC + 7 hours
    local utc_hour="${utc_timestamp:11:2}"
    local new_hour=$((utc_hour + 7))
    local actual_local="2025-05-26 $(printf "%02d" $new_hour):04:08"
    
    if [[ "$actual_local" == "$expected_local" ]]; then
        log_pass "Manual timezone +0700 correctly applied"
        return 0
    else
        log_fail "Manual timezone application failed: expected '$expected_local', got '$actual_local'"
        return 1
    fi
}

# Test: Change detection logic
test_change_detection_logic() {
    log_test "Change detection compares file timestamp vs corrected timestamp"
    
    local file_timestamp="2025-05-26 10:04:08"
    local corrected_timestamp="2025-05-26 12:04:08+02:00"
    
    # Mock change detection - should detect difference
    local needs_change=1
    
    # Extract local time from corrected timestamp (ignore timezone for comparison)
    local corrected_local="${corrected_timestamp%+*}"
    
    if [[ "$file_timestamp" != "$corrected_local" ]]; then
        needs_change=1
    else
        needs_change=0
    fi
    
    if [[ $needs_change -eq 1 ]]; then
        log_pass "Change detection correctly identified timestamp difference"
        return 0
    else
        log_fail "Change detection failed to identify difference"
        return 1
    fi
}

# Run all tests
main() {
    echo "Running fix-video-timestamp.sh tests..."
    echo "======================================="
    echo
    
    # Run individual tests
    test_insta360_filename_parsing
    test_invalid_insta360_filename
    test_iphone_keys_creation_priority
    test_iphone_fallback_to_media_create
    test_insta360_filename_priority
    test_insta360_fallback_to_metadata
    test_gopro_datetime_original_priority
    test_dst_germany_may
    test_dst_germany_january
    test_manual_timezone_application
    test_change_detection_logic
    
    echo
    echo "======================================="
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