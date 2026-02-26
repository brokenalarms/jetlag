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
- `--overwrite-datetimeoriginal` — replaces DTO with filename-derived time + timezone (exists, but not surfaced in UI or clearly documented as the "filename is correct, EXIF is wrong" mode)
- Timezone mismatch detection — warns when provided timezone differs from DTO's embedded timezone
- `@@key=value` machine-readable output — already consumed by the macOS app

### New CLI arguments

| Arg | Purpose |
|-----|---------|
| `--correct-time YYYYMMDD_HHMMSS` | "This file was actually taken at this time." Manual override when neither EXIF nor filename has the right time. Mutually exclusive with `--infer-from-filename`. |
| `--infer-from-filename` | "The filename has the correct time, use it as source of truth." Equivalent to the existing `--overwrite-datetimeoriginal` behaviour for Insta360/DJI files but with clearer intent. Should emit a warning if DTO already has a timezone and the time matches — signalling the user probably wants timezone correction, not time correction. |

Both of these are **time correction** modes — they change the actual time, not just the timezone. They should:

1. Read the existing DTO/CreationDate/filename time
2. Calculate the delta between the old time and the correct time
3. In dry run: show the delta ("Offset: +3d 7h 22m 15s") and the before/after for each file
4. In apply: write the corrected time with timezone to all metadata fields
5. Emit `@@time_offset_seconds=N` and `@@time_offset_display=+3d 7h 22m 15s` for the macOS app

### Interaction with `--timezone`

- `--correct-time` + `--timezone`: corrects both time and timezone. The correct time is interpreted as local time in the provided timezone.
- `--infer-from-filename` + `--timezone`: uses filename time + provided timezone as source of truth (existing `--overwrite-datetimeoriginal` behaviour, reframed).
- `--correct-time` without `--timezone`: error — must know the timezone to write correct metadata.
- `--infer-from-filename` without `--timezone`: error unless DTO already has a timezone embedded (in which case, warn that this looks like a pure time correction).

### Signals and warnings

The script should provide intelligent signals about what it's doing, especially when the data is ambiguous:

| Scenario | Signal |
|----------|--------|
| DTO has timezone, user provides same timezone, no time correction args | `@@timestamp_action=no_change` — everything matches, nothing to do |
| DTO has timezone, user provides different timezone, no `--overwrite-*` | `@@timestamp_action=tz_mismatch` — existing behaviour, refuses without force flag |
| DTO has timezone matching user's, but `--correct-time` differs from DTO time | Time correction mode — apply offset, emit `@@time_offset_seconds=N` |
| `--infer-from-filename` but filename time matches DTO time | Warn: "Filename and DTO agree — time correction unnecessary. Did you mean timezone correction?" |
| `--infer-from-filename` but file has no parseable filename timestamp | Error: "Cannot infer time from filename — use `--correct-time` instead" |
| `--overwrite-datetimeoriginal` used without `--infer-from-filename` or `--correct-time` | Existing behaviour preserved for backwards compat, but deprecation notice pointing to the new flags |

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

New machine-readable lines:
- `@@time_offset_seconds=10717414` — raw delta for programmatic use
- `@@time_offset_display=+124d 1h 3m 34s` — human-friendly for UI display
- `@@correction_mode=time` vs `@@correction_mode=timezone` — tells the app which mode was used

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
| `--correct-time YYYYMMDD_HHMMSS` | `--correct-time` |
| `--infer-from-filename` | `--infer-from-filename` |

These are mutually exclusive with each other. Both require `--timezone`.

### Batch offset concept

The bash `offset-filename-datetime.sh` calculates the offset from ONE reference file, then applies it to ALL files. In the pipeline, this works naturally:

1. **All files get the same `--correct-time` or `--infer-from-filename`** — the offset is per-file (each file's own filename/DTO vs the corrected time)
2. **For the "reference file" pattern**: the user picks one file, enters the correct time, and the app calculates the offset once. Then it passes `--correct-time` to each file with that file's own corrected time (original time + offset).

This means the app needs to:
1. Let the user pick a reference file and enter the correct time
2. Calculate `offset = correct_time - reference_file_time`
3. For each file: `file_correct_time = file_original_time + offset`
4. Pass per-file `--correct-time` to fix-media-timestamp.py

Alternatively, a simpler approach: add `--time-offset +/-SECONDS` to fix-media-timestamp.py, so the pipeline just passes one offset to every file. This avoids the app needing to pre-read every file's time.

**Recommendation: `--time-offset` is simpler.** The app calculates the offset from the reference file, then passes `--time-offset=+10717414` to fix-media-timestamp.py for every file. The script applies the offset to whatever timestamp source it finds (DTO, filename, etc).

### New arg (preferred approach)

| Arg | Purpose |
|-----|---------|
| `--time-offset [+/-]SECONDS` | Apply this delta to the file's existing timestamp. Requires `--timezone`. |

This replaces the per-file `--correct-time` approach. The script:
1. Reads the existing best timestamp (same 5-tier priority as today)
2. Adds the offset in seconds
3. Writes the corrected time + timezone to all metadata fields

## macOS app changes

### 1. Surface `--overwrite-datetimeoriginal` / `--infer-from-filename`

The fix timezone step currently has one control: the timezone picker. Add a toggle:

**"Use filename as source of truth"** (maps to `--infer-from-filename`)
- Help text: "Use when the camera's embedded EXIF time is wrong but the filename has the correct time. Common for Insta360 and DJI cameras after a factory reset."
- When toggled on:
  - Show a note: "Filename timestamp will replace DateTimeOriginal"
  - If the selected profile has no filename-parseable patterns (check against known patterns), show a warning

### 2. Time correction mode

Add a second mode to the fix timezone step — effectively making it "Fix Time & Timezone":

**Mode selector** (radio/segmented):
- **Timezone only** (default) — existing behaviour, just adds/fixes timezone
- **Time correction** — enables the offset UI:
  - Reference file picker (Browse button, shows selected filename)
  - "Correct time" input field (YYYYMMDD_HHMMSS format, with inline validation)
  - Computed offset display: "Offset: +3d 7h 22m 15s" (computed live from reference file's time vs entered correct time)
  - This requires reading the reference file's timestamp at selection time — a quick exiftool call from the app

The app computes the offset (`correct_time - reference_file_time`) and passes `--time-offset=SECONDS --timezone=+HHMM` to the pipeline.

### 3. Rename the pipeline step

`Fix Timezone` → `Fix Timestamps` (or `Fix Time`)

The step now handles both timezone correction and time correction. The label should reflect this. Update:
- `PipelineStep.fixTimezone` → `PipelineStep.fixTimestamps`
- `Strings.Pipeline.fixTimezoneLabel` → `Strings.Pipeline.fixTimestampsLabel`
- `Strings.Pipeline.fixTimezoneHelp` — update help text to mention both modes
- Task name stays `fix-timestamp` (already correct)

### 4. Show offset in diff table

When time correction is used, the diff table should show:
- `originalTime` — as today
- `correctedTime` — as today, but now includes the offset
- New annotation or tooltip showing the offset applied

The `@@time_offset_display` machine line provides this for each file.

### 5. New Strings

```swift
enum Pipeline {
    static let fixTimestampsLabel = "Fix Timestamps"
    static let fixTimestampsHelp = "Correct timezone labelling and/or camera clock errors"
}

enum Workflow {
    static let correctionModeLabel = "Correction type"
    static let timezoneOnlyOption = "Timezone"
    static let timeCorrectionOption = "Time correction"

    static let referenceFileLabel = "Reference file"
    static let referenceFilePlaceholder = "Select a file with known correct time"
    static let correctTimeLabel = "Correct time"
    static let correctTimePlaceholder = "YYYYMMDD_HHMMSS"
    static let correctTimeFormatHelp = "Enter the correct time for the reference file"
    static let computedOffsetLabel = "Offset"

    static let inferFromFilenameToggle = "Use filename as source of truth"
    static let inferFromFilenameHelp = "Use when embedded EXIF time is wrong but the filename has the correct capture time"

    static let timezoneAlreadyInDTO = "This file already has a timezone in DateTimeOriginal"
    static let timeCorrectionUnnecessary = "Filename and EXIF time agree — did you mean timezone correction?"
}
```

### 6. WorkflowSession additions

```swift
// New properties
var correctionMode: CorrectionMode = .timezoneOnly  // .timezoneOnly or .timeCorrection
var referenceFilePath: String = ""
var correctTime: String = ""  // YYYYMMDD_HHMMSS
var inferFromFilename: Bool = false
var computedOffsetSeconds: Int? = nil  // calculated when reference file + correct time are set

enum CorrectionMode: String, CaseIterable {
    case timezoneOnly = "timezone"
    case timeCorrection = "time"
}
```

### 7. buildPipelineArgs changes

When `correctionMode == .timeCorrection`:
- If `computedOffsetSeconds` is set: pass `--time-offset=+/-SECONDS`
- Always pass `--timezone`
- Pass `--overwrite-datetimeoriginal` (needed for the script to apply the corrected time)

When `inferFromFilename` is toggled:
- Pass `--infer-from-filename` (or `--overwrite-datetimeoriginal` until the new flag is implemented)

## Implementation order

### Phase 1: Script (`scripts/`)
1. Add `--time-offset [+/-]SECONDS` to `fix-media-timestamp.py`
2. Add `--infer-from-filename` as alias/replacement for `--overwrite-datetimeoriginal`
3. Emit `@@time_offset_seconds`, `@@time_offset_display`, `@@correction_mode` machine lines
4. Smart warnings (filename matches DTO, no filename pattern found, etc.)
5. Tests: offset calculation, filename inference, warning triggers, companion file handling

### Phase 2: Pipeline (`scripts/`)
6. Add `--time-offset` and `--infer-from-filename` pass-through in `media-pipeline.py`
7. Test pipeline end-to-end with time correction mode

### Phase 3: macOS app (`macos/`)
8. Rename step: `fixTimezone` → `fixTimestamps`
9. Add correction mode selector (timezone only vs time correction)
10. Add reference file picker + correct time input + live offset display
11. Add infer-from-filename toggle
12. Wire up `buildPipelineArgs()` for new flags
13. Parse new `@@` lines in `parseMachineReadableLine()`
14. Update diff table to show offset info

## What this does NOT cover

- **Filename renaming** — `offset-filename-datetime.sh` renames files (VID_20250101_120000.mp4 → VID_20250505_130334.mp4). The pipeline doesn't rename files; it writes metadata. Filename renaming could be a separate future feature.
- **Automatic clock drift detection** — comparing timestamps across cameras to detect drift automatically. Would require analyzing multiple files from multiple cameras together. Future feature.
- **Timeline visualization** — covered in the separate `todos/timeline-visualization.md` spec, but the `@@time_offset_*` data feeds directly into showing before/after positions.
