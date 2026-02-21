# Test Suite Summary

## Overview

Comprehensive test suite for media timestamp fixing, tagging, and organization scripts. Tests focus on real-world scenarios, business logic, and regression prevention.

## Test Files Created

### Unit Tests (Testing Functions Directly)

**`test_fix_media_timestamp_units.py`**
- Tests individual functions in fix-media-timestamp.py
- Validates timestamp parsing, calculations, EXIF operations
- Focuses on data structures and return values
- Key areas:
  - Timezone parsing and normalization
  - File system timestamp operations (birth time only)
  - EXIF cache behavior
  - Change detection logic (what needs updating)
  - 5-tier priority system for finding best timestamp

**`test_tag_media_units.py`**
- Tests individual functions in tag-media.py
- Validates check-before-write behavior (idempotency)
- Key areas:
  - Getting existing Finder tags
  - Adding tags (only missing ones)
  - Getting existing EXIF camera data
  - Adding EXIF data (only missing fields)
  - Dry run vs apply mode
  - Data/presentation separation

### Scenario Tests (Testing Real Use Cases)

**`test_timezone_scenarios.py`** ⭐ Most Important
- Tests real-world timezone combinations
- Validates actual user workflows
- Key scenarios:
  - **Viewing in Japan (+09:00), shot in Taiwan (+08:00)**
    - Shot: 2025-06-18 07:25:21+08:00
    - UTC: 2025-06-17 23:25:21
    - Display in Japan: 2025-06-18 08:25:21
  - **Preserve wallclock shooting time** (always show 07:25:21)
  - **Timezone boundary date changes** (crossing midnight)
  - **Negative timezones** (e.g., New York -05:00)
  - **UTC to local conversion** (files with only UTC timestamps)
  - **Video editor compatibility** (birth time for import, Keys:CreationDate for timeline)
  - **End-to-end workflow** (import → fix → organize)

### Integration Tests (Testing Complete Workflows)

**`test_organize_by_date.py`**
- Tests organize-by-date.py (via organize-by-date.sh wrapper)
- Validates file organization and template substitution
- Key areas:
  - Dry run vs apply mode
  - Template variable substitution ({{YYYY}}, {{MM}}, {{DD}}, {{LABEL}})
  - Directory creation
  - Idempotency (detecting already-organized files)
  - Multiple files with same date

**`test_fix_media_timestamp.py`**
- Integration tests for fix-media-timestamp.py
- Tests complete script execution
- Key areas:
  - Command-line argument handling
  - Multiple file types
  - Error conditions

**`test_tag_media.py`**
- Integration tests for tag-media.py
- Tests complete tagging workflow
- Key areas:
  - Combined tags + EXIF operations
  - Multiple files
  - Unsupported file types

## Running Tests

```bash
# Simple - just run this
python3 run-tests.py

# Specific scenarios
python3 run-tests.py test_timezone_scenarios.py

# One specific test
python3 run-tests.py test_timezone_scenarios.py::TestTimezoneScenarios::test_scenario_viewing_in_japan_shot_in_taiwan -v
```

## Key Principles Validated

### 1. Data/Presentation Separation (CLAUDE.md)
```python
# ✅ Good: Functions return data
success, tags_added = apply_finder_tags(file, ["tag1", "tag2"])
assert isinstance(tags_added, list)

# ❌ Bad: Functions return formatted strings
result = apply_finder_tags(file, ["tag1", "tag2"])
assert "Tagged: file.mp4" in result  # Brittle!
```

### 2. Check Before Write (Idempotency)
```python
# First run: adds tags
success, added = apply_finder_tags(file, ["tag1"], apply=True)
assert len(added) == 1

# Second run: nothing to add
success, added = apply_finder_tags(file, ["tag1"], apply=True)
assert len(added) == 0
```

### 3. Birth Time Only (Not Modification Time)
```python
# Only birth time is set
set_file_system_timestamps(file, "2025:06:18 07:25:21")

# Modification time changes naturally (from exiftool writes)
# Not artificially set to match birth time
```

### 4. Real Scenarios (Not Just Unit Tests)
```python
# Test actual user scenario
video = create_video_shot_in_timezone(
    "taiwan.mp4",
    "2025:06:18 07:25:21",
    "+08:00"
)

# Verify it displays correctly in Japan (+09:00)
# Should show 08:25:21, not 07:25:21
```

## Regression Protection

These tests lock in current behavior for:

1. **Timezone handling** - Shot in TZ A, view in TZ B shows correct time
2. **Idempotency** - Running scripts twice is safe
3. **Birth time only** - Modification time not artificially set
4. **Check before write** - Tags/EXIF only written when needed
5. **Video editor compatibility** - Birth time for import, Keys:CreationDate for timeline
6. **Template substitution** - {{YYYY}}-{{MM}}-{{DD}} works correctly
7. **Dry run mode** - Shows what will change without changing anything

## Coverage Areas

| Script | Unit Tests | Scenario Tests | Integration Tests |
|--------|-----------|----------------|------------------|
| fix-media-timestamp.py | ✅ | ✅ | ✅ |
| tag-media.py | ✅ | - | ✅ |
| organize-by-date.py | ✅ | - | ✅ |
| media-pipeline.py | - | ✅ (workflow) | - |

## Example Test Output

```
$ python3 run-tests.py test_timezone_scenarios.py -v

test_timezone_scenarios.py::TestTimezoneScenarios::test_scenario_viewing_in_japan_shot_in_taiwan PASSED
test_timezone_scenarios.py::TestTimezoneScenarios::test_scenario_preserve_wallclock_shooting_time PASSED
test_timezone_scenarios.py::TestTimezoneScenarios::test_scenario_timezone_boundary_date_change PASSED
test_timezone_scenarios.py::TestVideoEditorBehavior::test_import_screen_uses_birth_time PASSED
test_timezone_scenarios.py::TestRealWorldWorkflow::test_workflow_import_fix_organize PASSED

================================ 5 passed in 12.34s ================================
```

## Next Steps

When adding new features:

1. Add unit tests for new functions
2. Add scenario tests for timezone behavior
3. Add integration tests for complete workflows
4. Run tests before committing: `python3 run-tests.py`

## Dependencies

```bash
pip install -r tests/requirements.txt
```

System dependencies:
- ffmpeg (for creating test videos)
- exiftool (for metadata operations)
- tag (for macOS Finder tags)
- SetFile (for setting birth time, from Xcode CLI tools)
