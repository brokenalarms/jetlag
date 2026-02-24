# Replace conftest auto-skip with explicit decorators

## Context

The conftest.py source-inspection mechanism (`_uses_macos_features`, `_get_test_source`, `pytest_collection_modifyitems`) scans test source code for string indicators like `"tag"`, `"SetFile"`, `st_birthtime` to auto-skip tests on Linux. This is opaque — you can't tell by looking at a test class whether it will be skipped. It also misses indirect macOS dependencies (e.g. tests that call `fix-media-timestamp.py --apply`, which internally uses `SetFile`).

Replace with explicit `@pytest.mark.skipif(sys.platform != "darwin", reason="requires macOS")` decorators on each macOS-only class. Then remove all the auto-skip machinery from conftest.py.

## Changes

### 1. Add `@pytest.mark.skipif(sys.platform != "darwin", reason="requires macOS")` to these classes:

**`test_fix_media_timestamp.py`** — 2 classes:
- `TestFixMediaTimestamp`
- `TestFixMediaTimestampIntegration` (already has decorator, normalize it)

**`test_fix_media_timestamp_units.py`** — 3 classes:
- `TestExifDataReading`
- `TestChangeDetection`
- `TestDetermineNeededChanges`

**`test_tag_media.py`** — 2 classes:
- `TestTagMedia`
- `TestTagMediaDataPresentation`

**`test_tag_media_units.py`** — 3 classes:
- `TestGetExistingTags`
- `TestApplyFinderTags`
- `TestIdempotency` (whole class — test_exif_idempotent loses Linux coverage, acceptable)

**`test_timestamp_regression.py`** — 5 classes:
- `TestFilenameSourceOfTruth`
- `TestDateTimeOriginalPreservation`
- `TestTimezoneConversion`
- `TestMissingDateTimeOriginalWithTimezoneChange`
- `TestBirthTimeCalculation`

**`test_timezone_scenarios.py`** — 3 classes:
- `TestTimezoneScenarios`
- `TestVideoEditorBehavior`
- `TestRealWorldWorkflow`

### 2. Remove auto-skip machinery from `conftest.py`

Delete: `_get_test_source()`, `_uses_macos_features()`, `pytest_collection_modifyitems()`

Keep: tool installation, `pytest_addoption`, `pytest_configure`

### 3. Each file needs `import sys` if not already present

## Files to modify

- `scripts/tests/conftest.py`
- `scripts/tests/test_fix_media_timestamp.py`
- `scripts/tests/test_fix_media_timestamp_units.py`
- `scripts/tests/test_tag_media.py`
- `scripts/tests/test_tag_media_units.py`
- `scripts/tests/test_timestamp_regression.py`
- `scripts/tests/test_timezone_scenarios.py`

## Verification

1. Run tests locally (macOS) — all tests still run, none newly skipped
2. Push and check CI (Linux) — macOS-only classes skipped, cross-platform tests pass
3. Grep for `_uses_macos` and `_get_test_source` to confirm removal is complete
