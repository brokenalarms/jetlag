# Media Scripts Test Suite

Comprehensive tests for media timestamp fixing, tagging, and organization scripts.

## Test Structure

Each `test_*.py` module opens with a docstring saying what it protects; read that first. The suites fall into four groups:

### Unit tests
Call functions directly and assert on returned data, not output strings.

- `test_fix_media_timestamp_units.py` — timezone parsing and normalisation, birth-time operations, change detection, the priority order for picking the best timestamp
- `test_tag_media_units.py` — reading and adding Finder tags and EXIF camera fields, only adding what is missing, dry run vs apply
- `test_fix_timestamp_plan.py` — `plan_correction` and `apply_correction`: source ranking, declared-zone relabelling, the `--force-timezone` gate, `--time-offset` and the one-write rule
- `test_pipeline_stages.py`, `test_pipeline_preflight.py`, `test_pipeline_consent.py` — which stages a run's options route a file through, the stage loop's completion and failure exit, the timezone pre-flight decision, and the consent prompts (each file also holds the end-to-end tests of its area)
- `test_filesystem.py`, `test_timestamp_source.py`, `test_footage.py` — `lib/` modules

Unit tests that would otherwise call exiftool take the `fake_metadata` fixture
(`conftest.py`): reads return the tags a test gives each path and writes are
recorded, with no exiftool process behind them.

### Scenario tests
Real timezone combinations users hit.

- `test_timezone_scenarios.py` — viewing in a different timezone from the one shot in, preserving wall-clock shooting time, UTC conversion and date-boundary crossing, video-editor behaviour (birth time for import, `Keys:CreationDate` for the timeline), and the import → fix → organise workflow

### Integration and regression tests
Run a script end to end against temporary media and compare file state before and after.

- media-pipeline, split by area: `test_pipeline_cli.py` (arguments, modes, summary, JSONL events), `test_pipeline_discovery.py`, `test_pipeline_timezones.py`, `test_pipeline_organize.py`, `test_pipeline_companions.py`, `test_pipeline_archive.py`, `test_pipeline_working_dir.py`, `test_pipeline_cancel.py`; `pipeline_helpers.py` runs the pipeline as the app does, and the `temp_workspace` / `test_profile` fixtures are in `conftest.py`
- `test_timestamp_regression.py`, `test_fix_media_timestamp.py`, `test_tag_media.py`, `test_organize_by_date.py`, `test_ingest_media.py`, `test_archive_source.py`, `test_generate_gyroflow.py`, `test_probe_camera.py`, `test_scan_source.py`, `test_report_file_dates.py`, `test_insta360_camera.py`

### Contract tests
Hold an interface or a cost fixed.

- `test_pipeline_schema.py` — the pipeline's JSONL output and its parser's tasks and flags match `scripts/pipeline-schema.yaml`
- `test_metadata_call_contract.py` — exact exiftool call counts per file (see `docs/testing.md`)
- `test_metadata_stderr.py`, `test_process_hygiene.py`, `test_xmp_namespace.py` — the long-lived exiftool client and the XMP namespace
- `test_requirements.py`, `test_python_compatibility.py` — runtime dependencies and the Python version macOS ships

## Required External Tools

Tests must never be skipped because a tool is missing. `conftest.py` auto-installs missing tools before collection, and refuses to start when a Python package from `scripts/requirements.txt` is missing:

| Tool | Where it comes from |
|------|---------|
| ffmpeg (creates test media) | auto-installed by `conftest.py` (`brew install ffmpeg` / `apt-get install ffmpeg`) |
| exiftool | vendored in `scripts/tools/`. Some tests call `exiftool` directly, so it must also be on `PATH` (see Running Tests) |
| tag (macOS) | vendored in `scripts/tools/` |
| SetFile (macOS) | required on macOS: `xcode-select --install` |

On Linux, tests that need macOS-only behaviour (Finder tags, birth time) carry `skipif` markers. All other tests must pass — no skipping.

**Never use `pytest.skip()` for missing tools.** If a test needs a tool, add it to `conftest.py` so it gets installed automatically.

## Running Tests

Python dependencies: runtime packages are in `scripts/requirements.txt`, test and lint
tooling in `scripts/requirements-dev.txt`. `make test-scripts` builds `scripts/.venv`
from both and runs the suite in parallel (stopping at the first failure). The pytest
settings (`pythonpath`, `testpaths`) live in the root `pyproject.toml`, so run pytest
from the repository root.

```bash
# Whole suite
make test-scripts

# Linux: exiftool is not on PATH there
PATH=$PWD/scripts/tools:$PATH make test-scripts

# Specific file, class or test
scripts/.venv/bin/pytest scripts/tests/test_timezone_scenarios.py
scripts/.venv/bin/pytest scripts/tests/test_timezone_scenarios.py::TestTimezoneScenarios::test_scenario_viewing_in_japan_shot_in_taiwan

# Lint
make lint
```

Per-platform notes, including the tests known to fail when running as root, are in `docs/environment.md`.

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
```python
# Good: functions return data
success, tags_added = apply_finder_tags(file, ["tag1", "tag2"])
assert isinstance(tags_added, list)

# Bad: asserting on a formatted string is brittle
assert "Tagged: file.mp4" in result
```

### Birth Time Only
```
Only the file's birth time is set. Its modification time changes naturally
when exiftool writes, and is never set to match the birth time.
```

## Design Principles

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

### pytest refuses to start with "Required tool ... not installed"
Install the missing tool named in the error — see the Required External Tools table above.

### `exiftool: not found` (Linux)
Put the vendored copy on `PATH`: `PATH=$PWD/scripts/tools:$PATH`.

## Adding New Tests

When adding features:

1. **Add unit tests** for new functions (test data structures)
2. **Add scenario tests** for timezone behavior (test real use cases)
3. **Add integration tests** for end-to-end workflows
4. **Update this README** with new scenarios

## Test Philosophy

- **Test behavior, not implementation** - Validate data structures and file effects
- **Test real scenarios** - Use actual timezone combinations users face
- **Avoid brittle tests** - Don't test log output strings unless critical
- **Test idempotency** - Running twice should be safe
- **Test composition** - Functions should work together correctly
