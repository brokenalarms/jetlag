# Time correction as a pipeline feature

## Problem

Jetlag's `fix-timestamp` step handles one scenario: **the camera clock was right, but the timezone was wrong or missing**. It pairs a local time from DateTimeOriginal with a timezone offset and writes the corrected metadata.

But there's a second, equally common scenario: **the camera clock was simply wrong**. An Insta360 reset to factory defaults, a GoPro that drifted, a camera set to the wrong date after a battery swap. The local time recorded in EXIF/filename is incorrect — not just in the wrong timezone, but genuinely the wrong hour or day.

Today this is handled by a standalone bash script (`offset-filename-datetime.sh`) that:
1. Takes a reference file with a known-wrong timestamp
2. Takes the correct timestamp for that file
3. Calculates the delta in seconds
4. Applies the same delta to all matching Insta360 files (VID_/IMG_/LRV_ patterns)
5. Renames files and updates metadata

This works, but it's bash-only, Insta360-specific, not integrated into the pipeline, and not surfaced in the macOS app.

## Design: extend `fix-media-timestamp.py`, not a new script

Rather than creating a parallel script, time correction should be incorporated into the existing `fix-media-timestamp.py`. The script already has the infrastructure:

- `parse_filename_timestamp()` — recognises VID_/IMG_/LRV_/DJI_/DSC_ filename patterns
- `--overwrite-datetimeoriginal` — safety gate that allows overwriting DTO even when it already contains timezone metadata. Where the replacement timestamp comes from is determined separately by the data source priority. Exists but not surfaced in the UI.
- Timezone mismatch detection — warns when provided timezone differs from DTO's embedded timezone
- `@@key=value` machine-readable output — already consumed by the macOS app

### Two orthogonal axes

Time correction involves two independent decisions:

**Axis 1 — Where to read the source time from:**

| Flag | Reads time from | When to use |
|------|----------------|-------------|
| *(default)* | DateTimeOriginal / CreationDate / MediaCreateDate (existing 5-tier priority) | Camera EXIF has the right local time, just needs timezone |
| `--infer-from-filename` | Filename timestamp (VID_YYYYMMDD_HHMMSS, DJI_*, etc) | Camera EXIF is corrupt/wrong, but the filename recorded the correct capture time |

**Axis 2 — Whether to overwrite existing timezone in DTO:**

| Flag | Behaviour | When to use |
|------|-----------|-------------|
| *(default)* | Refuse if DTO already has timezone embedded (`@@timestamp_action=tz_mismatch`) | Normal operation — don't accidentally overwrite correct metadata |
| `--overwrite-datetimeoriginal` | Overwrite DTO even if it already has timezone | You know the existing tz in DTO is wrong and want to replace it |

These are orthogonal. Any combination is valid:

| Infer from filename? | Overwrite DTO? | Use case |
|---------------------|----------------|----------|
| No | No | Standard timezone fix: DTO has right time, no tz, add it |
| No | Yes | DTO has time + wrong tz, keep the time but replace the tz |
| Yes | No | EXIF is missing/corrupt, filename has right time, DTO has no tz yet |
| Yes | Yes | EXIF has wrong time + wrong tz, filename is correct, overwrite everything |

### Time offset (the new capability)

In addition to the two axes above, add a third concept for batch clock correction:

| Arg | Purpose |
|-----|---------|
| `--time-offset [+/-]SECONDS` | Apply this delta to the file's existing timestamp. For when the camera clock was simply wrong by a fixed amount. |

This works with either data source (EXIF or filename). The script:
1. Reads the best timestamp (from EXIF or filename depending on flags)
2. Adds the offset in seconds
3. Writes the corrected time + timezone to all metadata fields
4. Requires `--timezone`
5. Does NOT imply `--overwrite-datetimeoriginal` — the safety gate is always independent. If DTO already has timezone metadata, the script still returns `tz_mismatch` unless `--overwrite-datetimeoriginal` is explicitly provided. In the app this translates to a warning dialog, not an auto-bypass.

Dry run output:
```
Original : 2025-01-01 12:00:00 (DateTimeOriginal)
Corrected: 2025-05-05 13:03:34+09:00 (time correction)
Offset   : +124d 1h 3m 34s
```

New machine-readable lines:
- `@@time_offset_seconds=10717414` — raw delta for programmatic use
- `@@time_offset_display=+124d 1h 3m 34s` — human-friendly for UI display
- `@@correction_mode=time` vs `@@correction_mode=timezone` — tells the app which mode was used

### Interaction with `--timezone`

- `--time-offset` requires `--timezone` — must know the timezone to write correct metadata
- `--infer-from-filename` requires `--timezone` — the filename has no tz, so one must be provided
- `--infer-from-filename` without `--timezone`: error
- `--time-offset` + `--infer-from-filename`: valid — read from filename, apply offset, write with timezone

### Signals and warnings

| Scenario | Signal |
|----------|--------|
| DTO has timezone, user provides same timezone, no overwrite flag | `@@timestamp_action=no_change` — everything matches, nothing to do |
| DTO has timezone, user provides different timezone, no overwrite flag | `@@timestamp_action=tz_mismatch` — existing behaviour, refuses. Script emits warning with hint about `--overwrite-datetimeoriginal` |
| DTO has timezone, user provides `--overwrite-datetimeoriginal` | Proceeds with overwrite, emits warning to stderr for awareness |
| `--infer-from-filename` but file has no parseable filename timestamp | Error: "Cannot infer time from filename — no recognised pattern" |
| `--infer-from-filename` and filename time matches DTO time | Info: "Filename and DTO agree on time — applying timezone only" (not an error, just informational) |

### Dry run diff output

Currently dry run shows:
```
Original : 2025-05-14 02:07:00 (DateTimeOriginal)
Corrected: 2025-05-14 09:07:00+09:00 (timezone fix)
```

With time correction, it should also show:
```
Original : 2025-01-01 12:00:00 (DateTimeOriginal)
Corrected: 2025-05-05 13:03:34+09:00 (time correction)
Offset   : +124d 1h 3m 34s (applied from reference)
```

## Pipeline integration (`media-pipeline.py`)

The existing `fix-timestamp` task stays as-is. Time correction and filename renaming are additional flags on the same step, not separate tasks:

```
INGEST → [tag] → [fix-timestamp] → [rename-dates] → [organize] → [gyroflow] → [archive-source]
                       ↑                  ↑
              writes corrected       renames working copy
              metadata               if filename has date
                       │                  ↑
                       └──── @@corrected_time=... ────┘
```

### New pipeline args passed to `fix-media-timestamp.py`

| Arg | Purpose |
|-----|---------|
| `--time-offset [+/-]SECONDS` | Apply delta to file's best timestamp |
| `--infer-from-filename` | Read source time from filename instead of EXIF |

Both require `--timezone`. Neither implies `--overwrite-datetimeoriginal` — the safety gate is always independent.

### Pre-flight: `report-file-dates.py` (new script)

A lightweight script the macOS app runs **before** the pipeline to report what timestamp data is available. Uses the same `lib/timestamp_source.py` as `fix-media-timestamp.py`, ensuring both always agree on what's available. Not part of `media-pipeline.py` — runs independently.

| Arg | Purpose |
|-----|---------|
| `<source-dir>` | Directory to scan (nested) |

Calls `read_timestamp_sources()` on each file and aggregates results. Emits:
- `@@all_parseable=true/false` — whether every media file has a parseable date in its filename
- `@@parseable_count=N` / `@@total_count=N` — counts for UI display

The app uses `@@all_parseable` to control whether the "From filenames" timestamp source option is available.

### Rename step: `rename-file-dates.py` (new script)

A lightweight script that renames a file's date portion if the filename has a parseable date pattern. Completely independent of `fix-media-timestamp.py` — it takes a file and a corrected timestamp, and renames accordingly.

| Arg | Purpose |
|-----|---------|
| `--corrected-time YYYY-MM-DD_HH:MM:SS` | The corrected timestamp to write into the filename |
| `--dry-run` | Preview the rename without applying |

The script:
1. Calls `read_timestamp_sources()` from `lib/timestamp_source.py` — checks `report.filename_parseable` and `report.filename_pattern`
2. If filename has a parseable date → generates corrected filename via `build_filename()`, renames the working copy
3. If filename has no parseable date → no-op, emits `@@rename_action=no_date_pattern`
4. Emits `@@renamed_to=<new_filename>` on success

`media-pipeline.py` reads `@@renamed_to` and updates `active_file` so downstream steps (organize, gyroflow) pick up the new filename.

The rename is available whenever a filename has a parseable date — regardless of whether the corrected timestamp came from EXIF metadata or filename inference, or whether an offset was applied. It is not tied to `--time-offset` or `--infer-from-filename`.

### Batch offset flow

The user enters a manual offset (or calculates one externally). The pipeline applies it uniformly:

1. The app passes `--time-offset=+/-SECONDS --timezone=+HHMM` to `media-pipeline.py`
2. The pipeline passes the same `--time-offset` to every `fix-media-timestamp.py` invocation
3. Each file reads its own best timestamp, applies the offset, writes corrected metadata
4. `fix-media-timestamp.py` emits `@@corrected_time=...` for each file
5. If rename step is enabled, the pipeline passes `@@corrected_time` to `rename-file-dates.py`

## macOS app changes

### 1. Rename the pipeline step

`Fix Timezone` → `Fix Timestamps`

The step handles timezone correction and (now) time correction. Update:
- `PipelineStep.fixTimezone` → `PipelineStep.fixTimestamps`
- `Strings.Pipeline.fixTimezoneLabel` → `Strings.Pipeline.fixTimestampsLabel`
- `Strings.Pipeline.fixTimezoneHelp` → update help text to cover both capabilities
- Task name stays `fix-timestamp` (already correct)

### 2. Fix Timestamps step layout

All options live within the single Fix Timestamps step, progressively disclosed:

**Timestamp source** — selector at the top of the step:

| Option | When visible | Behaviour |
|--------|-------------|-----------|
| **Metadata** (default) | Always | Reads timestamp from the existing tiered EXIF priority system. Shows a sample preview: the date found from the first file + whether timezone is present or missing. |
| **From filenames** | Only when pre-flight reports all files have parseable filename dates | Reads timestamp from filename patterns. Shows the first file as a sample: filename displayed with parsed date in demo boxes (date, time, tz — tz likely missing since filenames rarely encode it). Text below: "All files in this group must follow this naming format." |

When "From filenames" is selected, maps to `--infer-from-filename`. Also enables the "Update filename dates" toggle (default ON) since filenames are the source of truth and will need updating after correction.

**Timezone picker** — always visible, always required (unchanged from today).

**Time offset** — optional field for batch clock correction. Enter offset as seconds or human-readable (e.g. `+3d 7h 22m 15s`). Applies the same delta to every file in the batch. When provided, maps to `--time-offset=+/-SECONDS`.

**"Update filename dates" toggle** — only visible when pre-flight reports parseable filename dates. **Default ON when "From filenames" is selected** (the filenames will need updating). When enabled, the pipeline runs `rename-file-dates.py` after fix-timestamp to update the filename's date portion to match the corrected time.

### Pre-flight: file parser script

Before the pipeline runs, the macOS app invokes `report-file-dates.py` on the source folder. This uses the same `lib/timestamp_source.py` as `fix-media-timestamp.py`, so both always agree.

The script calls `read_timestamp_sources()` on each file. For the first file, the full `TimestampReport` provides the sample preview data. Reports results via `@@` lines:
- `@@all_parseable=true/false` — controls "From filenames" option visibility
- `@@parseable_count=N` / `@@total_count=N` — counts
- `@@sample_file=<filename>` — first file used for previews
- `@@sample_metadata_date=<datetime>` — from `report.metadata_date`
- `@@sample_metadata_tz=present/missing` — from `report.metadata_tz`
- `@@sample_filename_date=<datetime>` — from `report.filename_date`
- `@@sample_filename_pattern=<pattern>` — from `report.filename_pattern`

The app uses these to populate the timestamp source preview boxes and control option visibility.

### 3. Overwrite DTO handling (safety gate → UI warning gate)

`--overwrite-datetimeoriginal` is never auto-bypassed, not even by `--time-offset`. In the app:

- When a dry run returns files with `@@timestamp_action=tz_mismatch`, show a warning in the diff table: "Timezone already present in metadata — differs from provided timezone"
- Offer a "Force overwrite" action (per-file or global) that re-runs with `--overwrite-datetimeoriginal`
- The script's safety gate always maps to a UI warning gate — the user must consciously confirm

### 4. Filename date renaming

Source files are never modified — only read, then at most moved to an archive folder. When filenames encode timestamps (VID_YYYYMMDD_HHMMSS, DJI_*, etc) and the time is corrected, the filename date is now wrong.

The "Update filename dates" toggle (visible when pre-flight reports parseable dates, default ON when "From filenames" source is selected) controls this. When enabled:
- The pipeline runs `rename-file-dates.py` on the working copy after `fix-media-timestamp.py` completes
- The corrected timestamp is passed via `--corrected-time` (from `@@corrected_time` emitted by fix-media-timestamp.py)
- The working copy is renamed in-place; `active_file` is updated via `@@renamed_to`
- Downstream steps (organize, gyroflow) see the correctly-named file

### 5. Show offset in diff table

When time correction is used (offset is non-zero), the diff table shows:
- `originalTime` — as today
- `correctedTime` — as today, but with the corrected time
- New annotation or tooltip showing the offset applied

The `@@time_offset_display` machine line provides this for each file.

### 6. New Strings

```swift
enum Pipeline {
    static let fixTimestampsLabel = "Fix Timestamps"
    static let fixTimestampsHelp = "Correct timezone labelling and/or camera clock errors"
}

enum Workflow {
    static let timestampSourceLabel = "Timestamp source"
    static let timestampSourceMetadata = "Metadata"
    static let timestampSourceFilenames = "From filenames"

    static let sampleMetadataDate = "Sample: %@ — timezone %@"  // e.g. "Sample: 2025-05-14 02:07:00 — timezone missing"
    static let sampleFilenameFormat = "All files in this group must follow this naming format"

    static let timeOffsetLabel = "Time offset"
    static let timeOffsetPlaceholder = "e.g. +3600 or +1h 0m 0s"
    static let timeOffsetHelp = "Apply this offset to every file's timestamp"

    static let updateFilenameDatesToggle = "Update filename dates"
    static let updateFilenameDatesHelp = "Rename files so filename dates match corrected timestamps"

    static let tzMismatchWarning = "Timezone already present in metadata — differs from provided timezone"
    static let forceOverwriteButton = "Overwrite existing timezone"
}
```

### 7. WorkflowSession additions

```swift
enum TimestampSource: String, CaseIterable {
    case metadata = "metadata"      // default — read from EXIF tiered priority
    case fromFilenames = "filenames" // read from filename date patterns
}

// New properties
var timestampSource: TimestampSource = .metadata
var timeOffsetSeconds: Int? = nil       // manual offset entry, nil = no offset
var updateFilenameDates: Bool = false   // enable rename-file-dates step (default ON when source is .fromFilenames)

// Pre-flight results (populated by report-file-dates.py before pipeline runs)
var allFilenamesParseable: Bool = false // controls whether .fromFilenames option is available
var sampleMetadataDate: String? = nil   // e.g. "2025-05-14 02:07:00"
var sampleMetadataTz: String? = nil     // "present" or "missing"
var sampleFilenameDate: String? = nil   // e.g. "2025-05-14 02:07:00"
var sampleFilenamePattern: String? = nil // e.g. "VID_YYYYMMDD_HHMMSS"
```

### 8. buildPipelineArgs changes

Always pass `--timezone` when the step is enabled (no change).

When `timestampSource == .fromFilenames`:
- Pass `--infer-from-filename`

When `timeOffsetSeconds` is non-nil and non-zero:
- Pass `--time-offset=+/-SECONDS`

When `updateFilenameDates` is toggled:
- Pipeline enables the `rename-file-dates` step after fix-timestamp
- Passes `--corrected-time` from `@@corrected_time` emitted by fix-media-timestamp.py

When user confirms force overwrite after tz_mismatch warning:
- Pass `--overwrite-datetimeoriginal`

## Shared lib — extracting the tiered timestamp reader

`fix-media-timestamp.py` is 1118 lines. Rather than extracting small string-parsing utils, the valuable reusable piece is the **timestamp analysis pipeline itself** — the logic that reads a file and reports what timestamps are available from which sources.

### `lib/timestamp_source.py` — "what does this file have?"

Extract the read-side analysis from `fix-media-timestamp.py` into a shared lib. This is the same tiered priority system that already exists, exposed as a reusable function:

```python
@dataclass
class TimestampReport:
    """Everything known about a file's timestamps from all sources."""
    # Best timestamp from EXIF (5-tier priority)
    metadata_date: Optional[datetime]   # e.g. 2025-05-14 02:07:00
    metadata_source: str                # e.g. "DateTimeOriginal with timezone", "filename"
    metadata_tz: Optional[str]          # e.g. "+09:00" or None if missing

    # Filename analysis
    filename_parseable: bool
    filename_date: Optional[datetime]   # parsed from VID_YYYYMMDD_HHMMSS etc
    filename_pattern: Optional[str]     # e.g. "VID_YYYYMMDD_HHMMSS"

def read_timestamp_sources(file_path: str) -> TimestampReport:
    """Analyse a file and report all available timestamp sources."""
```

This extracts the core of:
- `read_exif_data()` — reads EXIF fields via exiftool (cached)
- `get_best_timestamp()` — 5-tier priority selection
- `parse_filename_timestamp()` — filename pattern matching for VID/IMG/LRV/DJI/DSC/macOS patterns
- `extract_metadata_timezone()` — timezone extraction from DTO/CreationDate

Both scripts use the same lib, so they always agree:
- **`report-file-dates.py`** calls `read_timestamp_sources()` on each file, aggregates results, reports `@@` lines for the app's preview
- **`fix-media-timestamp.py`** calls `read_timestamp_sources()` to get the same analysis, then uses `report.metadata_date` or `report.filename_date` depending on `--infer-from-filename`. The read logic is shared — only the "what to do with it" differs

This also means `rename-file-dates.py` can use `report.filename_parseable` and `report.filename_pattern` to determine if/how to rename, rather than duplicating the pattern matching.

### `build_filename()` — reverse of parse (also in lib)

The lib also needs the reverse operation for renaming:
```python
def build_filename(original_name: str, corrected_date: datetime) -> Optional[str]:
    """Generate corrected filename by replacing the date portion, preserving prefix/suffix/ext."""
```

### What stays in `fix-media-timestamp.py`

Everything that decides and writes stays in the main script:
- `get_all_timestamp_data()` — orchestration: reads the report, applies timezone/overwrite logic, computes UTC
- EXIF write functions — tightly coupled to exiftool
- Change detection — tightly coupled to write decisions
- `fix_media_timestamps()` — main orchestrator
- Display/formatting functions

### Already in `lib/` (unchanged)
- `lib/exiftool.py` — persistent exiftool subprocess (used by `timestamp_source.py`)
- `lib/file_timestamps.py` — macOS file system timestamps
- `lib/filesystem.py` — `find_media_files()`, `parse_machine_output()`

## Implementation order

### Phase 0: Extract shared timestamp reader (`scripts/lib/`)
1. Create `lib/timestamp_source.py` — `read_timestamp_sources()` returns `TimestampReport` with metadata date/tz/source + filename parseability/date/pattern. Also `build_filename()` for reverse name generation.
2. Extract `read_exif_data()`, `get_best_timestamp()`, `parse_filename_timestamp()`, `extract_metadata_timezone()` from `fix-media-timestamp.py` into the lib
3. Refactor `fix-media-timestamp.py` to import from lib, verify existing tests still pass

### Phase 1: Script — infer from filename (`scripts/`)
4. Add `--infer-from-filename` flag to `fix-media-timestamp.py` — uses `report.filename_date` from `lib/timestamp_source.py` instead of `report.metadata_date`, requires `--timezone`
5. Keep `--overwrite-datetimeoriginal` as the orthogonal safety gate (unchanged)
6. Emit `@@corrected_time=YYYY-MM-DD_HH:MM:SS` for every file (needed by rename step)
7. Tests: filename inference for VID_/IMG_/LRV_/DJI_ patterns, interaction with --overwrite-datetimeoriginal, error when no parseable filename

### Phase 2: Script — time offset (`scripts/`)
8. Add `--time-offset [+/-]SECONDS` to `fix-media-timestamp.py` — applies delta to the timestamp from `TimestampReport`
9. Does NOT imply `--overwrite-datetimeoriginal` — safety gate always independent
10. Emit `@@time_offset_seconds`, `@@time_offset_display`, `@@correction_mode` machine lines
11. Tests: offset calculation, positive/negative offsets, interaction with `--infer-from-filename`, tz_mismatch still fires when DTO has tz

### Phase 3: Scripts — filename scanning + renaming (`scripts/`)
12. Create `report-file-dates.py` — pre-flight script using `lib/timestamp_source.py` to scan a folder and report what's available
13. Emits `@@all_parseable=true/false`, `@@parseable_count`, `@@total_count`, per-file `@@file_date=<name>|<datetime>`
14. Tests: mixed parseable/unparseable folders, nested directories, all-parseable vs partial
15. Create `rename-file-dates.py` — standalone script that renames a file's date portion
16. Takes `--corrected-time` and the file path; uses `read_timestamp_sources()` and `build_filename()` from `lib/timestamp_source.py`
17. Emits `@@renamed_to=<new_filename>` on success, `@@rename_action=no_date_pattern` if no parseable date
18. Source files are never modified — this operates on the working copy only
19. Tests: reverse-generation for all supported patterns, no-op when no date in filename, companion file handling

### Phase 4: Pipeline integration (`scripts/`)
20. Add `--time-offset`, `--infer-from-filename` pass-through to fix-media-timestamp.py in `media-pipeline.py`
21. Add `rename-file-dates` as a new pipeline step after fix-timestamp, conditionally enabled
22. Pipeline reads `@@corrected_time` from fix-timestamp, passes to rename step
23. Pipeline reads `@@renamed_to` from rename step, updates `active_file`
24. Test pipeline end-to-end with time correction + rename

### Phase 5: macOS app (`macos/`)
25. Rename step: `fixTimezone` → `fixTimestamps`
26. Pre-flight: run `report-file-dates.py` on source folder, populate sample preview data
27. Timestamp source selector: Metadata (with sample date + tz status) / From filenames (with sample filename demo boxes + format note)
28. Time offset field — optional manual offset entry
29. "Update filename dates" toggle (visible when parseable dates, default ON when source is filenames)
30. Handle tz_mismatch: show warning, offer force overwrite
31. Wire up `buildPipelineArgs()` for new flags
32. Parse new `@@` lines in `parseMachineReadableLine()`
33. Show offset in diff table

## What this does NOT cover

- **Automatic clock drift detection** — comparing timestamps across cameras to detect drift automatically. Would require analyzing multiple files from multiple cameras together. Future feature.
- **Timeline visualization** — covered separately in TODO.md, but the `@@time_offset_*` data feeds directly into showing before/after positions.
