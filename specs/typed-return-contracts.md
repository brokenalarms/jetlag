# Typed return contracts for pipeline scripts

## Problem

Every script called by `media-pipeline.py` communicates results via `@@key=value` lines on stdout — an ad-hoc text protocol with no schema, no type safety, and no validation. The caller parses raw strings and hopes the keys match. Adding a field means updating the print site, the parser, and the caller — with nothing catching mismatches.

This is the first step in a three-part migration:
1. **Typed return contracts** (this spec) — functions return dataclasses, `main()` serialises them
2. **Subprocess → module calls** — callers import and call directly, receive typed objects
3. **JSONL + schema for app IPC** — replace `@@` with structured output at the process boundary

## Design

Each script gets a result dataclass. The function returns it. `@@` lines are only consumed by the macOS app via `media-pipeline.py`'s `emit()` — individual scripts don't need to emit them. With typed returns, `media-pipeline.py` reads the dataclass fields and emits `@@` (or later JSONL) itself. The scripts' `main()` functions can print human-readable summaries to stderr for CLI use, but no `@@` serialisation is needed there.

### `tag-media.py`

`tag_media_file()` already returns a dict — replace with:

```python
@dataclass
class TagResult:
    file: str
    tags_added: list[str]
    exif_make: str
    exif_model: str
    action: str  # "tagged" | "already_correct"
```

The function returns `TagResult | None` (None on failure).

### `fix-media-timestamp.py`

`fix_media_timestamps()` currently prints `@@` lines inline and returns `bool`. Refactor to return:

```python
@dataclass
class TimestampFixResult:
    file: str
    original_time: str
    corrected_time: str
    timestamp_source: str
    timestamp_action: str  # "fixed" | "would_fix" | "no_change" | "error" | "tz_mismatch"
    timezone: str          # detected timezone, empty if none
```

The function returns `TimestampFixResult`. All `print(f"@@...")` calls inside the function are removed — replaced with populating the dataclass fields. `media-pipeline.py` reads the fields and emits `@@`/JSONL at the process boundary.

This is the largest change — the `@@` prints are currently scattered across 5+ code paths (early returns, success, error). Each becomes a field assignment on the result object.

### `organize-by-date.py`

`process_file()` already returns `(dest, action)` — wrap in:

```python
@dataclass
class OrganizeResult:
    dest: str
    action: str  # "copied" | "moved" | "skipped" | "overwrote" | "would_copy" | "would_move" | "would_overwrite"
```

### `generate-gyroflow.py`

`main()` currently handles everything. Extract the core logic into a function returning:

```python
@dataclass
class GyroflowResult:
    gyroflow_path: str
    action: str  # "generated" | "skipped" | "would_generate"
    error: str   # empty on success
```

### `archive-source.py`

Already returns `int` (return code). Add:

```python
@dataclass
class ArchiveResult:
    action: str  # "archived" | "deleted" | "would_archive" | "would_delete"
    failed: bool
```

### No serialisation helper needed in scripts

`@@` output was only consumed by the macOS app. With typed returns, `media-pipeline.py` handles all serialisation at the process boundary. Individual scripts just return dataclasses. Their `main()` functions print human-readable output to stderr for CLI users.

## Implementation order

1. Add dataclasses to each script (no behavior change yet)
2. Refactor functions to build and return the dataclass
3. Replace inline `print(f"@@...")` with `emit_result()` in `main()`
4. Verify all existing tests pass — output should be identical

Do `fix-media-timestamp.py` last since it has the most scattered `@@` prints.

## Files to modify

- `scripts/tag-media.py` — add `TagResult`, refactor `tag_media_file()`
- `scripts/fix-media-timestamp.py` — add `TimestampFixResult`, refactor `fix_media_timestamps()`
- `scripts/organize-by-date.py` — add `OrganizeResult`, refactor `process_file()`
- `scripts/generate-gyroflow.py` — add `GyroflowResult`, extract function from `main()`
- `scripts/archive-source.py` — add `ArchiveResult`, refactor return values

## Verification

- All existing tests pass unchanged
- CLI output identical (same `@@key=value` lines, same stderr messages)
- `pyrefly check` passes

## Relationship to other specs

- **Prerequisite for**: subprocess → module calls spec (callers need typed returns to avoid text parsing)
- **Prerequisite for**: JSONL + schema spec (structured data enables schema-based serialisation)
- **Foundation for**: time-correction-pipeline-step.md (`TimestampFixResult` gets extended with `correction_mode`, `time_offset_seconds`, `time_offset_display` fields)
