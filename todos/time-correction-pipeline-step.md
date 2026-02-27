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

### Rename step: `rename-file-dates.py` (new script)

A lightweight script that renames a file's date portion if the filename has a parseable date pattern. Completely independent of `fix-media-timestamp.py` — it takes a file and a corrected timestamp, and renames accordingly.

| Arg | Purpose |
|-----|---------|
| `--corrected-time YYYY-MM-DD_HH:MM:SS` | The corrected timestamp to write into the filename |
| `--dry-run` | Preview the rename without applying |

The script:
1. Parses the filename using `parse_filename_date()` from `lib/transforms.py`
2. If filename has a parseable date → generates corrected filename via `build_filename()`, renames the working copy
3. If filename has no parseable date → no-op, emits `@@rename_action=no_date_pattern`
4. Emits `@@renamed_to=<new_filename>` on success

`media-pipeline.py` reads `@@renamed_to` and updates `active_file` so downstream steps (organize, gyroflow) pick up the new filename.

The rename is available whenever a filename has a parseable date — regardless of whether the corrected timestamp came from EXIF metadata, manual entry, or filename inference. It is not tied to `--time-offset` or `--infer-from-filename`.

### Batch offset concept

The bash `offset-filename-datetime.sh` calculates the offset from ONE reference file, then applies it to ALL files. In the pipeline:

1. The app lets the user pick a reference file and enter the correct time
2. The app calculates `offset = correct_time - reference_file_time` (one exiftool read)
3. The app passes `--time-offset=+/-SECONDS --timezone=+HHMM` to `media-pipeline.py`
4. The pipeline passes the same `--time-offset` to every `fix-media-timestamp.py` invocation
5. Each file reads its own best timestamp, applies the offset, writes corrected metadata
6. `fix-media-timestamp.py` emits `@@corrected_time=...` for each file
7. If rename step is enabled, the pipeline passes `@@corrected_time` to `rename-file-dates.py`

## macOS app changes

### 1. Rename the pipeline step

`Fix Timezone` → `Fix Timestamps`

The step handles timezone correction and (now) time correction. Update:
- `PipelineStep.fixTimezone` → `PipelineStep.fixTimestamps`
- `Strings.Pipeline.fixTimezoneLabel` → `Strings.Pipeline.fixTimestampsLabel`
- `Strings.Pipeline.fixTimezoneHelp` → update help text to cover both capabilities
- Task name stays `fix-timestamp` (already correct)

### 2. Fix Timestamps step layout

No mode selector. All options live within the single Fix Timestamps step, progressively disclosed:

**Timezone picker** — always visible, always required (unchanged from today).

**Amend time** — source selector for where to read the correct time from, defaulting to "From metadata" (auto-selected):

| Source | Behaviour |
|--------|-----------|
| From metadata (default) | Auto-reads existing EXIF timestamp via the 5-tier priority chain. This is today's behaviour — timezone-only correction. |
| Manual entry | Text field / time picker for directly typing the correct time (YYYYMMDD_HHMMSS format, with inline validation). |
| From file | File browser accepting absolute or `./` relative path. App parses the selected file's filename timestamp and fills the field. Shows error if filename pattern isn't recognised. |

When "From file" is selected:
- App scans the source directory (nested) for all matching files by filename pattern
- Parses all filename timestamps in advance to validate and preview
- Shows the reference file's parsed timestamp
- User enters the correct time → computed offset displayed live: "Offset: +3d 7h 22m 15s"
- Preview shows what all files would look like after applying the offset

When "Manual entry" is selected:
- Text field for correct time
- Same offset calculation and preview as "From file"

When the amend time source is anything other than "From metadata" and the entered time differs from the existing timestamp, the app computes the offset and passes `--time-offset=+/-SECONDS --timezone=+HHMM` to the pipeline.

### 3. Overwrite DTO handling (safety gate → UI warning gate)

`--overwrite-datetimeoriginal` is never auto-bypassed, not even by `--time-offset`. In the app:

- When a dry run returns files with `@@timestamp_action=tz_mismatch`, show a warning in the diff table: "Timezone already present in metadata — differs from provided timezone"
- Offer a "Force overwrite" action (per-file or global) that re-runs with `--overwrite-datetimeoriginal`
- The script's safety gate always maps to a UI warning gate — the user must consciously confirm

### 4. Filename date renaming

Source files are never modified — only read, then at most moved to an archive folder. When filenames encode timestamps (VID_YYYYMMDD_HHMMSS, DJI_*, etc) and the time is corrected, the filename date is now wrong.

Add a toggle within the Fix Timestamps step: **"Update filename dates to match corrected timestamps"**. This is available whenever the pipeline detects that the filename has a parseable date pattern — it's not tied to any particular correction mode.

When enabled:
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
    static let amendTimeLabel = "Amend time"
    static let fromMetadataOption = "From metadata"
    static let manualEntryOption = "Enter manually"
    static let fromFileOption = "From file"

    static let referenceFileLabel = "Reference file"
    static let referenceFilePlaceholder = "Select a file to read timestamp from"
    static let correctTimeLabel = "Correct time"
    static let correctTimePlaceholder = "YYYYMMDD_HHMMSS"
    static let correctTimeFormatHelp = "Enter the actual time this file was captured"
    static let computedOffsetLabel = "Offset"

    static let renameFileDatesToggle = "Update filename dates to match corrected timestamps"
    static let renameFileDatesHelp = "Rename working copy so filename date reflects the corrected time"

    static let tzMismatchWarning = "Timezone already present in metadata — differs from provided timezone"
    static let forceOverwriteButton = "Overwrite existing timezone"
}
```

### 7. WorkflowSession additions

```swift
// New properties
var amendTimeSource: AmendTimeSource = .fromMetadata
var referenceFilePath: String = ""
var correctTime: String = ""  // YYYYMMDD_HHMMSS
var computedOffsetSeconds: Int? = nil  // calculated when correct time differs from reference
var renameFileDates: Bool = false

enum AmendTimeSource: String, CaseIterable {
    case fromMetadata = "metadata"
    case manual = "manual"
    case fromFile = "file"
}
```

### 8. buildPipelineArgs changes

Always pass `--timezone` when the step is enabled (no change).

When `amendTimeSource == .fromFile`:
- Pass `--infer-from-filename`

When `computedOffsetSeconds` is non-nil and non-zero (time correction active):
- Pass `--time-offset=+/-SECONDS`

When `renameFileDates` is toggled:
- Pipeline enables the `rename-file-dates` step after fix-timestamp
- Passes `--corrected-time` from `@@corrected_time` emitted by fix-media-timestamp.py

When user confirms force overwrite after tz_mismatch warning:
- Pass `--overwrite-datetimeoriginal`

## Testable transforms — extracting generic building blocks

`fix-media-timestamp.py` is 1118 lines. The goal is not to split it into domain-specific files (that just spreads complexity). The goal is to extract **generic, pure transform functions** — small ETL-style conversions where each step can be unit tested in isolation without exiftool or real files.

### `lib/transforms.py` — pure conversion functions

These are the building blocks that the complex functions are composed from. Each takes a value in, returns a value out, no side effects:

| Transform | Input → Output | Example |
|-----------|---------------|---------|
| `parse_exif_datetime(s)` | `"2025:05:14 02:07:00"` → `datetime` | EXIF's colon-separated format → Python datetime |
| `parse_tz_offset(s)` | `"+09:00"` or `"+0900"` or `"9"` → `timedelta` | Any timezone string → timedelta (normalisation) |
| `format_exif_datetime(dt)` | `datetime` → `"2025:05:14 02:07:00+09:00"` | Reverse of parse |
| `apply_offset(dt, seconds)` | `(datetime, int)` → `datetime` | Add/subtract seconds from a timestamp |
| `parse_filename_date(name)` | `"VID_20250505_130334.mp4"` → `(prefix, datetime, suffix, ext)` | Decompose filename into parts |
| `build_filename(prefix, dt, suffix, ext)` | `("VID_", datetime, "", ".mp4")` → `"VID_20250505_130334.mp4"` | Reverse of parse |
| `format_offset_display(seconds)` | `10717414` → `"+124d 1h 3m 34s"` | Human-readable offset string |
| `country_to_tz(code, csv_path)` | `"JP"` → `"+09:00"` | Country code → timezone offset via CSV |
| `extract_tz_from_exif_value(s)` | `"2025:05:14 02:07:00+09:00"` → `"+09:00"` or `None` | Pull tz suffix from EXIF string |

These are generic and discoverable — any script dealing with timestamps, timezones, or media filenames can import them. Unit tests are trivial: pass a string in, assert a value out.

### What stays in `fix-media-timestamp.py`

Everything that orchestrates reads/writes/decisions stays in the main script:
- `get_best_timestamp()` — calls exiftool, applies priority chain (uses `parse_exif_datetime`, `extract_tz_from_exif_value` internally)
- `get_all_timestamp_data()` — orchestration logic
- EXIF write functions — tightly coupled to exiftool
- Change detection — tightly coupled to write decisions
- `fix_media_timestamps()` — main orchestrator
- Display/formatting functions — these call the transforms internally but also format for stdout/`@@` output

The transforms file doesn't replace any complex function — it provides the tested building blocks they're composed from. When adding `--time-offset`, the new logic is: `parse_exif_datetime` → `apply_offset` → `format_exif_datetime` — each step already tested.

### Already in `lib/` (unchanged)
- `lib/exiftool.py` — persistent exiftool subprocess
- `lib/file_timestamps.py` — macOS file system timestamps
- `lib/filesystem.py` — `find_media_files()`, `parse_machine_output()`

## Implementation order

### Phase 0: Extract testable transforms (`scripts/lib/`)
1. Create `lib/transforms.py` — pure conversion functions (parse/format EXIF datetimes, parse/build filenames, tz normalisation, offset arithmetic)
2. Unit tests for each transform: string in → value out, no exiftool or filesystem needed
3. Refactor `fix-media-timestamp.py` to call transforms internally, verify existing tests still pass

### Phase 1: Script — infer from filename (`scripts/`)
4. Add `--infer-from-filename` flag to `fix-media-timestamp.py` — reads time from filename using `parse_filename_date()` from `lib/transforms.py`, requires `--timezone`
5. Keep `--overwrite-datetimeoriginal` as the orthogonal safety gate (unchanged)
6. Emit `@@corrected_time=YYYY-MM-DD_HH:MM:SS` for every file (needed by rename step)
7. Tests: filename inference for VID_/IMG_/LRV_/DJI_ patterns, interaction with --overwrite-datetimeoriginal, error when no parseable filename

### Phase 2: Script — time offset (`scripts/`)
8. Add `--time-offset [+/-]SECONDS` to `fix-media-timestamp.py` — applies delta using `apply_offset()` from `lib/transforms.py`
9. Does NOT imply `--overwrite-datetimeoriginal` — safety gate always independent
10. Emit `@@time_offset_seconds`, `@@time_offset_display`, `@@correction_mode` machine lines
11. Tests: offset calculation, positive/negative offsets, interaction with `--infer-from-filename`, tz_mismatch still fires when DTO has tz

### Phase 3: Script — filename date renaming (`scripts/`)
12. Create `rename-file-dates.py` — standalone script that renames a file's date portion
13. Takes `--corrected-time` and the file path; uses `parse_filename_date()` / `build_filename()` from `lib/transforms.py`
14. Emits `@@renamed_to=<new_filename>` on success, `@@rename_action=no_date_pattern` if no parseable date
15. Source files are never modified — this operates on the working copy only
16. Tests: reverse-generation for all supported patterns, no-op when no date in filename, companion file handling

### Phase 4: Pipeline integration (`scripts/`)
17. Add `--time-offset`, `--infer-from-filename` pass-through to fix-media-timestamp.py in `media-pipeline.py`
18. Add `rename-file-dates` as a new pipeline step after fix-timestamp, conditionally enabled
19. Pipeline reads `@@corrected_time` from fix-timestamp, passes to rename step
20. Pipeline reads `@@renamed_to` from rename step, updates `active_file`
21. Test pipeline end-to-end with time correction + rename

### Phase 5: macOS app (`macos/`)
22. Rename step: `fixTimezone` → `fixTimestamps`
23. Add amend time source picker (from metadata / manual entry / from file)
24. From file: folder scanning, filename parsing, reference file selection
25. Correct time input + live offset computation + preview
26. Rename file dates toggle within Fix Timestamps step
27. Handle tz_mismatch: show warning, offer force overwrite
28. Wire up `buildPipelineArgs()` for new flags
29. Parse new `@@` lines in `parseMachineReadableLine()`
30. Show offset in diff table

## What this does NOT cover

- **Automatic clock drift detection** — comparing timestamps across cameras to detect drift automatically. Would require analyzing multiple files from multiple cameras together. Future feature.
- **Timeline visualization** — covered separately in TODO.md, but the `@@time_offset_*` data feeds directly into showing before/after positions.
