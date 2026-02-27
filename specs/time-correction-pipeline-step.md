# Time correction pipeline step

## Problem

Jetlag's `fix-timestamp` step handles one scenario: the camera clock was right, but the timezone was wrong or missing. A second, equally common scenario — the camera clock was simply wrong (reset, drifted, wrong date after battery swap) — is handled by a standalone bash script that's Insta360-specific and not in the pipeline.

This spec covers two things: a **refactor** that extracts reusable timestamp reading into a shared lib, and **new features** that use that lib to handle clock correction, filename-based timestamps, and filename renaming.

---

## Refactor: `lib/timestamp_source.py`

### Why

`fix-media-timestamp.py` contains the read-side analysis inline — the logic that asks "what timestamps does this file have, from which sources?" This is needed by multiple scripts (the fixer, a pre-flight scanner, a renamer) and must give consistent answers. Extracting it into a shared lib means one implementation, one set of tests, and guaranteed agreement between scripts.

### What moves out of `fix-media-timestamp.py`

| Function | Current location | What it does |
|----------|-----------------|--------------|
| `read_exif_data()` | line 149 | Cached exiftool read of 7 EXIF timestamp fields |
| `get_best_timestamp()` | line 372 | 6-tier priority selection (DTO+tz → CreationDate+tz → Keys:CreationDate Z → filename → DTO no tz → MediaCreateDate → file times) |
| `parse_filename_timestamp()` | line 253 | Filename date extraction (see "generic patterns" below) |
| `extract_metadata_timezone()` | line 862 | Timezone extraction from DTO/CreationDate |

Plus one new function:

| Function | What it does |
|----------|--------------|
| `build_filename()` | Reverse of parse — replace the date portion of a filename with a corrected date, preserving everything else |

### Public API

```python
@dataclass
class TimestampReport:
    """Everything known about a file's available timestamps."""
    # From EXIF (6-tier priority)
    metadata_date: Optional[datetime]   # best timestamp found
    metadata_source: str                # which tier it came from
    metadata_tz: Optional[str]          # timezone if present, else None

    # From filename
    filename_parseable: bool            # whether a date pattern was found
    filename_date: Optional[datetime]   # the parsed date
    filename_pattern: Optional[str]     # e.g. "YYYYMMDD_HHMMSS"

def read_timestamp_sources(file_path: str) -> TimestampReport:
    """Analyse a file and report all available timestamp sources."""

def build_filename(original_name: str, corrected_date: datetime) -> Optional[str]:
    """Replace the date portion of a filename, preserving prefix/suffix/ext.
    Returns None if filename has no parseable date pattern."""
```

### Generic filename date patterns

The current `parse_filename_timestamp()` matches specific prefixes (VID\_, IMG\_, LRV\_, DJI\_, DSC\_, Screenshot). The extracted version matches **date-shaped sequences** anywhere in the filename:

| Pattern | Example | Extracted |
|---------|---------|-----------|
| `YYYYMMDD_HHMMSS` | `VID_20250505_130334_00_001.mp4` | `2025-05-05 13:03:34` |
| `YYYYMMDDHHMMSS` | `DJI_20250505130334_0001.mp4` | `2025-05-05 13:03:34` |
| `YYYY-MM-DD` + time | `Screenshot 2025-05-05 at 13.03.34.png` | `2025-05-05 13:03:34` |
| `YYYYMMDD` (no time) | `DSC_20250505_001.jpg` | `2025-05-05 00:00:00` |

Prefix-agnostic — new cameras with novel prefixes (`INSV_`, `R360_`) work automatically as long as they embed a standard date format.

`build_filename()` uses the same pattern detection to locate the date portion and replace it, preserving everything before and after (prefix, suffix, sequence numbers, extension).

### What stays in `fix-media-timestamp.py`

Everything that **decides and writes**:
- `get_all_timestamp_data()` — orchestration: reads the TimestampReport, applies timezone/overwrite logic, computes UTC
- EXIF write functions — tightly coupled to exiftool write flow
- Change detection — `determine_needed_changes()`, `check_*_needs_update()`
- `fix_media_timestamps()` — main orchestrator
- Display/formatting functions
- CLI arg parsing

### Who uses the lib

| Script | Uses |
|--------|------|
| `fix-media-timestamp.py` | `read_timestamp_sources()` — replaces inline functions |
| `report-file-dates.py` | `read_timestamp_sources()` — pre-flight scanning |
| `rename-file-dates.py` | `build_filename()` + `TimestampReport.filename_parseable` |

---

## New features on `fix-media-timestamp.py`

Two new flags, both orthogonal to the existing `--overwrite-datetimeoriginal` safety gate:

### `--infer-from-filename`

Use `report.filename_date` instead of `report.metadata_date` as the source timestamp.

- Requires `--timezone` (filenames don't encode timezone)
- Error if the filename has no parseable date pattern
- The safety gate is independent: if DTO already has a timezone and differs from the provided one, `@@timestamp_action=tz_mismatch` still fires unless `--overwrite-datetimeoriginal` is also passed

### `--time-offset [+/-]SECONDS`

Apply a fixed delta to the source timestamp (whichever source is selected).

- Requires `--timezone`
- Does NOT imply `--overwrite-datetimeoriginal` — safety gate always independent
- Works with either data source (metadata or filename)
- Combinable: `--infer-from-filename --time-offset +3600 --timezone +09:00` reads from filename, adds 1 hour, writes with +09:00

### New `@@` output

| Key | When | Example |
|-----|------|---------|
| `@@corrected_time` | Always | `2025-05-05 13:03:34` |
| `@@correction_mode` | Always | `time` or `timezone` |
| `@@time_offset_seconds` | When offset used | `3600` |
| `@@time_offset_display` | When offset used | `+1h 0m 0s` |

### Existing behavior unchanged

| Flag | Behaviour |
|------|-----------|
| `--timezone` | Required (no change) |
| `--overwrite-datetimeoriginal` | Safety gate — refuse if DTO has tz unless this is passed (no change) |
| `--apply` | Dry run vs apply (no change) |
| `--preserve-wallclock-time` | File system timestamp handling (no change) |

---

## New scripts

### `report-file-dates.py` — pre-flight scanner

The macOS app runs this **before** the pipeline to discover what timestamp data is available across the source folder. Uses `read_timestamp_sources()` from the shared lib — same analysis `fix-media-timestamp.py` will use later, guaranteeing agreement.

**Args:** `<source-dir>` (positional), `--file-extensions` (from profile)

**Behaviour:** Scans directory recursively for media files. Calls `read_timestamp_sources()` on each. Uses the first file as a sample for preview data.

**Output:**

| Key | Purpose |
|-----|---------|
| `@@all_parseable` | `true`/`false` — every file has a parseable filename date |
| `@@parseable_count` | Count of files with parseable filename dates |
| `@@total_count` | Total media files found |
| `@@sample_file` | First file's name |
| `@@sample_metadata_date` | Metadata date from first file |
| `@@sample_metadata_tz` | `present` or `missing` |
| `@@sample_filename_date` | Filename date from first file (if parseable) |
| `@@sample_filename_pattern` | e.g. `YYYYMMDD_HHMMSS` |

### `rename-file-dates.py` — filename date updater

Renames the date portion of a working copy's filename to match a corrected timestamp. Also renames companion files with the same stem.

**Args:**

| Arg | Purpose |
|-----|---------|
| `<file>` | The working copy to rename |
| `--corrected-time YYYY-MM-DD_HH:MM:SS` | Timestamp to write into the filename |
| `--companion-extensions .lrv .thm ...` | Also rename companion files with same stem |
| `--dry-run` | Preview without renaming |

**Behaviour:**
1. Calls `read_timestamp_sources()` to check if filename has a parseable date
2. If yes: `build_filename()` generates the corrected name, renames the file
3. If `--companion-extensions`: finds files with same stem + each extension, renames them too (same date swap)
4. If no parseable date: no-op

**Output:**

| Key | When |
|-----|------|
| `@@renamed_to=<new_filename>` | Main file renamed |
| `@@companion_renamed=<old>\|<new>` | Each companion renamed |
| `@@rename_action=no_date_pattern` | Filename has no parseable date |

---

## Pipeline changes (`media-pipeline.py`)

### Updated step order

```
INGEST → [tag] → [fix-timestamp] → [rename-dates] → OUTPUT → [gyroflow] → [archive-source]
```

`rename-dates` is a new optional step between `fix-timestamp` and `OUTPUT`.

### Arg pass-through

The pipeline passes new args to `fix-media-timestamp.py`:
- `--infer-from-filename` (when timestamp source is filenames)
- `--time-offset +/-SECONDS` (when offset provided)

These are pipeline-level args that flow through unchanged.

### Data flow between steps

```
fix-timestamp emits @@corrected_time=2025-05-05_13:03:34
                          │
                          ▼
rename-dates receives --corrected-time 2025-05-05_13:03:34
                     receives --companion-extensions .lrv .thm (from profile)
                          │
                          ▼
rename-dates emits @@renamed_to=VID_20250505_130334_00_001.mp4
                          │
                          ▼
pipeline updates active_file → downstream steps see renamed file
```

### Companion extensions

`rename-file-dates.py` receives `--companion-extensions` from the profile's existing `companion_extensions` field (already used by ingest for copying companions to the working dir).

---

## macOS app changes

### Rename pipeline step

`Fix Timezone` → `Fix Timestamps`. The step now covers timezone correction and clock correction.

- `PipelineStep.fixTimezone` → `PipelineStep.fixTimestamps`
- Label: "Fix Timestamps"
- Help text: "Correct timezone labelling and/or camera clock errors"
- Task name stays `fix-timestamp` (pipeline arg unchanged)

### Pre-flight

Before the pipeline runs, invoke `report-file-dates.py` on the source folder. Parse the `@@sample_*` lines to populate preview data. `@@all_parseable` controls whether the "From filenames" option is available in the timestamp source selector.

### Fix Timestamps step UI

All options within the single step, progressively disclosed:

**Timestamp source** — selector at top:
- **Metadata** (default, always visible): reads from EXIF tiered priority. Shows sample: date + tz status from `@@sample_metadata_*`.
- **From filenames** (visible only when `@@all_parseable=true`): reads from filename patterns. Shows sample: parsed date + pattern from `@@sample_filename_*`.

**Timezone picker** — always visible, always required (unchanged).

**Time offset** — optional field. Seconds or human-readable (`+3d 7h 22m 15s`). Same delta applied to every file.

**Update filename dates** — toggle, visible when `@@all_parseable=true`. Default ON when "From filenames" is selected. Enables the `rename-dates` pipeline step.

### `buildPipelineArgs()` wiring

| Condition | Arg passed |
|-----------|-----------|
| Timestamp source = filenames | `--infer-from-filename` |
| Time offset non-zero | `--time-offset=+/-SECONDS` |
| Update filename dates ON | Enable `rename-dates` task |
| Force overwrite confirmed | `--overwrite-datetimeoriginal` |

### `parseMachineReadableLine()` new keys

`@@correction_mode`, `@@time_offset_seconds`, `@@time_offset_display`, `@@renamed_to`, `@@companion_renamed`

---

## Implementation phases

### Phase 0: Extract `lib/timestamp_source.py`

1. Create `lib/timestamp_source.py` with `TimestampReport`, `read_timestamp_sources()`, `build_filename()`
2. Move `read_exif_data()`, `get_best_timestamp()`, `parse_filename_timestamp()`, `extract_metadata_timezone()` from `fix-media-timestamp.py`
3. Rewrite `parse_filename_timestamp()` to use generic date patterns instead of prefix-specific matching
4. Refactor `fix-media-timestamp.py` to import from the lib
5. Existing tests must still pass — no behaviour change

### Phase 1: `--infer-from-filename`

6. Add flag to `fix-media-timestamp.py` — selects `report.filename_date` over `report.metadata_date`
7. Requires `--timezone`, error if no parseable filename date
8. Emit `@@corrected_time` for every file
9. Tests: various date patterns, interaction with `--overwrite-datetimeoriginal`, error cases

### Phase 2: `--time-offset`

10. Add flag to `fix-media-timestamp.py` — applies delta to selected source timestamp
11. Does NOT imply `--overwrite-datetimeoriginal`
12. Emit `@@time_offset_seconds`, `@@time_offset_display`, `@@correction_mode`
13. Tests: positive/negative offsets, combined with `--infer-from-filename`, safety gate still fires

### Phase 3: New scripts

14. Create `report-file-dates.py` — scans folder using `read_timestamp_sources()`, emits `@@` lines
15. Create `rename-file-dates.py` — renames file + companions using `build_filename()`
16. Tests: mixed parseable/unparseable folders, companion renaming, no-op when no date in filename

### Phase 4: Pipeline integration

17. Add `rename-dates` step to `media-pipeline.py` after `fix-timestamp`
18. Pass `--time-offset`, `--infer-from-filename` through to fix-timestamp
19. Read `@@corrected_time` from fix-timestamp, pass to rename step
20. Read `@@renamed_to` from rename step, update `active_file`
21. Tests: end-to-end pipeline with offset + rename

### Phase 5: macOS app

22. Rename: `fixTimezone` → `fixTimestamps`
23. Pre-flight: invoke `report-file-dates.py`, parse results
24. UI: timestamp source selector, time offset field, update filename dates toggle
25. `buildPipelineArgs()`: wire new flags
26. `parseMachineReadableLine()`: parse new `@@` keys

---

## Not covered

- **Per-profile `filename_timestamp_patterns`** — custom filename date patterns in `media-profiles.yaml` for cameras with non-standard formats. Generic detection covers all known cameras today. Future TODO when needed.
- **Automatic clock drift detection** — comparing timestamps across cameras to find drift. Requires multi-file, multi-camera analysis.
- **Timeline visualization** — covered separately in TODO.md; `@@time_offset_*` data feeds into it.
