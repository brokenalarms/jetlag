# Media Scripts Test Suite

Comprehensive tests for media timestamp fixing, tagging, and organization scripts.

## Test Structure

### Unit Tests
Test individual functions in isolation, focusing on data structures and return values rather than output strings.

- `test_fix_media_timestamp_units.py` - Unit tests for timestamp parsing, calculations, and EXIF operations
- `test_tag_media_units.py` - Unit tests for tag and EXIF read/write operations

### Scenario Tests
Test real-world timezone scenarios and workflows.

- `test_timezone_scenarios.py` - Comprehensive timezone handling tests covering:
  - Viewing in different timezones than shooting timezone
  - Preserve wallclock time vs display time modes
  - UTC conversions and date boundary crossing
  - Video editor compatibility behavior
  - End-to-end workflows

### Integration Tests
Test bash scripts and full workflows.

- `test_organize_by_date.py` - File organization and template substitution
- `test_fix_media_timestamp.py` - Full script execution tests
- `test_tag_media.py` - Full tagging workflow tests

## Required External Tools

Tests must never be skipped because a tool is missing. `conftest.py` auto-installs missing tools before collection:

| Tool | All platforms | macOS only | Install (manual fallback) |
|------|:---:|:---:|---------|
| ffmpeg | **auto-installed** | | `brew install ffmpeg` / `apt install ffmpeg` |
| exiftool | **auto-installed** | | `brew install exiftool` / `apt install libimage-exiftool-perl` |
| humanize (Python) | **auto-installed** | | `pip install humanize` |
| tag | | **required** | `brew install tag` |
| SetFile | | **required** | `xcode-select --install` |

On Linux, tests that call macOS-only tools (`tag`, `SetFile`) are skipped automatically by `conftest.py`. All other tests must pass — no skipping.

**Never use `pytest.skip()` for missing tools.** If a test needs a tool, add it to `conftest.py` so it gets installed automatically.

## Running Tests

### Prerequisites

```bash
# Install Python dependencies
pip install -r tests/requirements.txt

# Tools are auto-installed by conftest.py, but to verify manually:
ffmpeg -version
exiftool -ver

# macOS only
which tag SetFile
```

### Run All Tests

```bash
# Using Python runner (recommended)
python3 run-tests.py

# Or directly with pytest
cd tests && pytest -v
```

### Run Specific Tests

```bash
# Specific test file
python3 run-tests.py test_timezone_scenarios.py

# Specific test class
python3 run-tests.py test_timezone_scenarios.py::TestTimezoneScenarios

# Specific test
python3 run-tests.py test_timezone_scenarios.py::TestTimezoneScenarios::test_scenario_viewing_in_japan_shot_in_taiwan

# With coverage
python3 run-tests.py --cov=. --cov-report=html
```

## What We Test (and Don't Test)

### ✅ We Test
- **Business logic** - Our timestamp calculations, timezone handling, template substitution
- **Integration points** - How our code interacts with exiftool, file system, external scripts
- **Real scenarios** - Actual timezone combinations users face
- **Data structures** - Return values, data transformations
- **Side effects** - File modifications, metadata changes

### ❌ We Don't Test
- **Standard library functions** - datetime, os, subprocess (already tested by Python)
- **Third-party tools** - exiftool, ffmpeg behavior (trust they work)
- **Log output formatting** - Brittle and doesn't test actual functionality
- **Trivial getters/setters** - Simple pass-through functions

## Key Test Scenarios

### Timezone Scenario: Viewing in Japan, Shot in Taiwan
```
Shot: 2025-06-18 07:25:21 in Taiwan (+08:00)
UTC: 2025-06-17 23:25:21
Viewing in Japan (+09:00): 2025-06-18 08:25:21

Validates:
- DateTimeOriginal preserved: 2025:06:18 07:25:21+08:00
- Keys:CreationDate matches DateTimeOriginal
- QuickTime CreateDate in UTC: 2025:06:17 23:25:21
- File birth time adjusted for viewer timezone
```

### Idempotency Tests
```
Running scripts twice should:
- Not change files the second time
- Report "no changes needed"
- Not trigger exiftool writes
- Maintain file modification times
```

### Data/Presentation Separation
```
Functions should:
- Return structured data (tuples, lists, dicts)
- Not return formatted strings
- Let presentation layer handle formatting
- Enable composition and reuse
```

## Design Principles from AGENTS.md

These tests validate adherence to:

1. **Separation of data and presentation** - Functions return data, formatting is separate
2. **Check before write** - Scripts only modify when needed (idempotency)
3. **No hardcoded defaults** - Configuration from files/environment
4. **Functional composition** - Build complex operations from simple functions
5. **Birth time only** - Only set birth time, not modification time

## Test Fixtures

Tests create temporary files with controlled metadata to validate:
- EXIF data reading/writing
- File system timestamp operations
- Timezone conversions
- Template substitution
- Error handling

## Common Issues

### Tests failing due to timezone
Some tests depend on system timezone. If running in unexpected timezone, tests may need adjustment.

### pytest refuses to start with "Required tools not installed"
Install the missing tools listed in the error — see the Required External Tools table above.

## Adding New Tests

When adding features:

1. **Add unit tests** for new functions (test data structures)
2. **Add scenario tests** for timezone behavior (test real use cases)
3. **Add integration tests** for end-to-end workflows
4. **Update this README** with new scenarios

## Test Philosophy

Following AGENTS.md principles:

- **Test behavior, not implementation** - Validate data structures and file effects
- **Test real scenarios** - Use actual timezone combinations users face
- **Avoid brittle tests** - Don't test log output strings unless critical
- **Test idempotency** - Running twice should be safe
- **Test composition** - Functions should work together correctly
