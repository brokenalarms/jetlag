# Replace subprocess calls with module calls in media-pipeline

## Problem

`media-pipeline.py` calls 5 sibling Python scripts via `subprocess.run()` — Python spawning Python to call functions that return data. This adds ~100ms overhead per invocation (process creation, venv activation for the bash wrapper case), loses type safety, and requires serialising/deserialising data through `@@key=value` text.

One call (`organize-by-date`) goes through a bash wrapper (`organize-by-date.sh`) before reaching Python.

`ingest-media` already uses the correct pattern: `importlib.import_module("ingest-media")` + direct function call.

## Prerequisite

**Typed return contracts** (see `specs/typed-return-contracts.md`) — functions must return dataclasses, not print `@@` lines, before this migration can happen. Otherwise callers would need `contextlib.redirect_stdout` hacks to capture output.

## Current state

| Function | Calls | Method |
|----------|-------|--------|
| `run_ingest_media()` | `ingest-media.py` | **Direct module call** (already done) |
| `run_tag_media()` | `tag-media.py` | subprocess |
| `run_fix_timestamp()` | `fix-media-timestamp.py` | subprocess |
| `run_organize_by_date()` | `organize-by-date.sh` → `.py` | subprocess + bash |
| `run_generate_gyroflow()` | `generate-gyroflow.py` | subprocess |
| `run_archive_source()` | `archive-source.py` | subprocess |

## Design

### Module imports

Hyphenated filenames can't be normal Python imports. Use `importlib` (same pattern as `ingest-media`):

```python
import importlib
_tag_mod = importlib.import_module("tag-media")
_fix_ts_mod = importlib.import_module("fix-media-timestamp")
_organize_mod = importlib.import_module("organize-by-date")
_gyroflow_mod = importlib.import_module("generate-gyroflow")
_archive_mod = importlib.import_module("archive-source")
```

### Import side-effects to fix first

Two scripts register `signal.signal(SIGINT, ...)` at module level — importing them overrides media-pipeline's own handler. Move these to `main()`:

- `tag-media.py` line 22
- `fix-media-timestamp.py` line 23

(These moves are already staged in the current branch.)

### Rewritten functions

Each `run_*` function calls the module function directly and receives the typed dataclass:

**`run_tag_media()`**
```python
def run_tag_media(file_path, tags, make, model, apply):
    finder_tags = tags.split(",") if tags else []
    result = _tag_mod.tag_media_file(str(file_path), finder_tags, make, model, not apply)
    if result is None:
        return TagResult(...)  # error case
    return result
```

No more parsing `@@` from stdout. The caller receives `TagResult` directly.

**`run_fix_timestamp()`**

Signature changes: `location_args: list[str]` → `timezone_offset: Optional[str]`.

The `location_args` abstraction existed because subprocess needed CLI args. With a direct call, we pass the timezone string directly:

```python
def run_fix_timestamp(file_path, timezone_offset, apply, verbose):
    return _fix_ts_mod.fix_media_timestamps(
        str(file_path), dry_run=not apply, timezone_offset=timezone_offset,
    )
```

Callers that currently build `["--timezone", value]` or `["--location", value]` are updated to resolve the timezone upfront (using `_fix_ts_mod.get_timezone_for_country()` for location lookups).

**`run_organize_by_date()`**
```python
def run_organize_by_date(file_path, target_dir, template, apply, verbose):
    return _organize_mod.process_file(
        str(file_path), target_dir, template,
        copy_mode=False, overwrite=False, apply=apply, verbose=verbose,
    )
```

Eliminates the bash wrapper entirely — `organize-by-date.sh` becomes dead code for the pipeline path (still usable from CLI).

**`run_generate_gyroflow()`**
```python
def run_generate_gyroflow(file_path, preset_json, apply):
    return _gyroflow_mod.generate_for_file(file_path, preset_json, apply)
```

Requires the function extraction from `main()` done in the typed-return-contracts spec.

**`run_archive_source()`**
```python
def run_archive_source(source_dir, action, files, apply, verbose):
    if action == "archive":
        return _archive_mod.archive_source(source_dir, apply)
    elif action == "delete":
        return _archive_mod.delete_files(source_dir, files, apply)
    return 1
```

### `process_file()` updates

The orchestrator function `process_file()` currently:
1. Calls `run_*` which returns `(stderr_output, changed, at_lines, ...)`
2. Prints stderr with indentation
3. Emits `@@` keys via `emit()`

After migration:
1. Calls the function directly → receives dataclass
2. Stderr messages are printed by the function itself (no capture needed — they go directly to stderr)
3. Emits `@@` keys by reading dataclass fields, via `emit()`

The indentation (`  ` prefix on sub-script stderr) is lost. This is acceptable — the pipeline stage headers (`🏷️ Tagging...`, `🔧 Fixing timestamp...`) already provide visual hierarchy.

### Remove `subprocess` import

After all 5 migrations, `subprocess` is no longer used in `media-pipeline.py`.

## Implementation order

1. Fix signal handlers (already staged)
2. Migrate `run_tag_media()` — simplest, `tag_media_file()` already returns structured data
3. Migrate `run_organize_by_date()` — `process_file()` already returns `(dest, action)`
4. Migrate `run_archive_source()` — functions already have clean signatures
5. Migrate `run_generate_gyroflow()` — requires function extraction
6. Migrate `run_fix_timestamp()` — largest change due to `location_args` → `timezone_offset` refactor
7. Remove `subprocess` import, delete `_parse_at_lines()`, delete `emit_result()` and `@@` serialisation from each script's `main()`

## Files to modify

- `scripts/media-pipeline.py` — rewrite all `run_*` functions, update `process_file()` and `main()`
- `scripts/generate-gyroflow.py` — extract `generate_for_file()` from `main()`

## Verification

- All existing tests pass (pipeline tests exercise the full flow)
- `pyrefly check` passes
- `subprocess` no longer imported in media-pipeline.py
- Manual test: run pipeline in dry-run and apply modes, verify identical `@@` output and file operations

## Relationship to other specs

- **Depends on**: typed-return-contracts.md (functions must return dataclasses first — otherwise module callers would need to capture and parse `@@` text)
- **Deletes**: `@@` serialisation in each script's `main()` (added temporarily in step 2, now dead code since pipeline calls functions directly). `_parse_at_lines()` in media-pipeline.py also deleted.
- **Preserves**: `@@` in `media-pipeline.py`'s `emit()` — the app still depends on it. This is replaced in step 4 (JSONL).
- **Enables**: JSONL + schema spec (with module calls done, `@@` only exists in `media-pipeline.py`'s `emit()` — one place to replace atomically)
- **Foundation for**: time-correction-pipeline-step.md (inline rename logic imports `build_filename()` from shared lib — needs module-call architecture to work without subprocess)
