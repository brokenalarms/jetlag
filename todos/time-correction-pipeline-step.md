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

The existing `fix-timestamp` task stays as-is. Time correction is a **mode** of fix-timestamp, not a separate task. This keeps the pipeline simple:

```
INGEST → [tag] → [fix-timestamp] → OUTPUT → [gyroflow] → [archive-source]
                      ↑
            timezone mode (default)
            OR time correction mode
```

### New pipeline args

| Arg | Passed to fix-media-timestamp.py |
|-----|----------------------------------|
| `--time-offset [+/-]SECONDS` | `--time-offset` |
| `--infer-from-filename` | `--infer-from-filename` |

Both require `--timezone`. Neither implies `--overwrite-datetimeoriginal` — the safety gate is always independent.

### Batch offset concept

The bash `offset-filename-datetime.sh` calculates the offset from ONE reference file, then applies it to ALL files. In the pipeline:

1. The app lets the user pick a reference file and enter the correct time
2. The app calculates `offset = correct_time - reference_file_time` (one exiftool read)
3. The app passes `--time-offset=+/-SECONDS --timezone=+HHMM` to `media-pipeline.py`
4. The pipeline passes the same `--time-offset` to every `fix-media-timestamp.py` invocation
5. Each file reads its own best timestamp, applies the offset, writes corrected metadata

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

### 4. Filename renaming in output

Source files are never modified — only read, then at most moved to an archive folder. When filenames encode timestamps (VID_YYYYMMDD_HHMMSS, DJI_*, etc) and a time offset is applied, the filename is now wrong.

Add an option in the OUTPUT/organize step: **"Rename files to match corrected timestamps"** (maps to `--rename-files` in the organize step). Uses `parse_filename_timestamp()` pattern in reverse to generate corrected filenames when writing to the target directory.

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

    static let renameFilesToggle = "Rename files to match corrected timestamps"
    static let renameFilesHelp = "Update filename timestamps in output directory to reflect corrected time"

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
var renameFiles: Bool = false

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

When `renameFiles` is toggled:
- Pass `--rename-files`

When user confirms force overwrite after tz_mismatch warning:
- Pass `--overwrite-datetimeoriginal`

## Implementation order

### Phase 1: Script — infer from filename (`scripts/`)
1. Add `--infer-from-filename` flag to `fix-media-timestamp.py` — reads time from filename using existing `parse_filename_timestamp()`, requires `--timezone`
2. Keep `--overwrite-datetimeoriginal` as the orthogonal safety gate (unchanged)
3. Tests: filename inference for VID_/IMG_/LRV_/DJI_ patterns, interaction with --overwrite-datetimeoriginal, error when no parseable filename

### Phase 2: Script — time offset (`scripts/`)
4. Add `--time-offset [+/-]SECONDS` to `fix-media-timestamp.py` — applies delta to whatever timestamp source is found
5. Does NOT imply `--overwrite-datetimeoriginal` — safety gate always independent
6. Emit `@@time_offset_seconds`, `@@time_offset_display`, `@@correction_mode` machine lines
7. Tests: offset calculation, positive/negative offsets, interaction with `--infer-from-filename`, tz_mismatch still fires when DTO has tz

### Phase 3: Script — filename renaming (`scripts/`)
8. Add `--rename-files` flag to the organize/output step — renames files in the target directory to match corrected timestamps
9. Uses `parse_filename_timestamp()` pattern in reverse to generate corrected filenames
10. Source files are never modified — renaming only applies to output copies
11. Tests: VID_/IMG_/LRV_/DJI_ pattern reverse-generation, companion file renaming

### Phase 4: Pipeline pass-through (`scripts/`)
12. Add `--time-offset`, `--infer-from-filename`, `--rename-files` pass-through in `media-pipeline.py`
13. Test pipeline end-to-end with time correction + rename

### Phase 5: macOS app (`macos/`)
14. Rename step: `fixTimezone` → `fixTimestamps`
15. Add amend time source picker (from metadata / manual entry / from file)
16. From file: folder scanning, filename parsing, reference file selection
17. Correct time input + live offset computation + preview
18. Rename files toggle in output step
19. Handle tz_mismatch: show warning, offer force overwrite
20. Wire up `buildPipelineArgs()` for new flags
21. Parse new `@@` lines in `parseMachineReadableLine()`
22. Show offset in diff table

## What this does NOT cover

- **Automatic clock drift detection** — comparing timestamps across cameras to detect drift automatically. Would require analyzing multiple files from multiple cameras together. Future feature.
- **Timeline visualization** — covered separately in TODO.md, but the `@@time_offset_*` data feeds directly into showing before/after positions.
