# Dry-run diff table

Replace raw log output during dry-run with a structured table showing per-file
before/after state.  The log stays available behind a toggle for debugging.

## Design principles

- Scripts emit `@@key=value` on **stdout**, human text on **stderr**
  (already the convention in `organize-by-date.py`, `ingest-media.py`,
  `generate-gyroflow.py`).
- `media-pipeline.py` already captures stdout/stderr separately for each
  child script; it parses `@@` lines from stdout and passes stderr through.
- The macOS app's `ScriptRunner` already tags lines by stream
  (`LogLine.Stream.stdout` / `.stderr`).
- `LogOutputView` currently shows both streams, coloring `@@` lines blue.
  This is the thing being replaced.

## Scripts changes

### 1. Fix stdout/stderr consistency in tag-media.py

`tag-media.py` currently prints human-readable output (`📌 Tagged: ...`,
`✓ Already tagged correctly`) to **stdout**.  All other scripts use stderr
for human text.  Move these to `file=sys.stderr` for consistency.

### 2. New `@@` output from tag-media.py

After processing a file, emit on stdout:

```
@@file=<basename>
@@tags_added=<comma-separated list, or empty>
@@exif_make=<value or empty>
@@exif_model=<value or empty>
@@tag_action=tagged | already_correct
```

These are emitted from `tag_media_file()` alongside the existing human output
(which moves to stderr per step 1).

### 3. New `@@` output from fix-media-timestamp.py

`fix-media-timestamp.py` already emits `@@timezone=`.  Add (from
`fix_media_timestamps()`):

```
@@file=<basename>
@@original_time=<DateTimeOriginal as-read, e.g. 2025:05:14 16:38:07+02:00>
@@corrected_time=<corrected DateTimeOriginal with timezone, same format>
@@timestamp_source=<source description, e.g. "DateTimeOriginal with timezone">
@@timestamp_action=would_fix | no_change | fixed | error
```

`@@timezone=` is already emitted.  Keep it.

The existing human-readable output (`🔍`, `📅`, `⏱️`, `🌐`, `📊` lines)
already goes to stderr (via `print()` default stdout — **check**: some may
need moving to stderr).  Audit and fix.

**Audit result**: `fix_media_timestamps()` uses bare `print()` for all its
emoji output, which goes to stdout.  These must move to `file=sys.stderr`.
The only line that should stay on stdout is `@@timezone=` (and the new
`@@` lines).

### 4. Propagate `@@` lines through media-pipeline.py

`media-pipeline.py` currently:
- Captures stdout+stderr from child scripts as combined `output`
- Prints each line with `print(f"  {line}")`

Change `run_tag_media()` and `run_fix_timestamp()` to:
- Separate stdout (for `@@` parsing) from stderr (for display)
- Re-emit parsed `@@` lines on its own stdout (so the macOS app sees them)
- Print stderr lines to its own stderr for human display

`run_organize_by_date()` and `run_ingest_media()` already separate
stdout/stderr correctly.  `run_tag_media()` and `run_fix_timestamp()` use
`capture_output=True` then merge — these need fixing.

After each file, emit a summary `@@` line:

```
@@pipeline_file=<basename>
@@pipeline_result=changed | unchanged | failed
```

### 5. `organize-by-date.py` — already fine

Already emits `@@dest=` and `@@action=` on stdout, human text on stderr.
No changes needed.

### 6. `ingest-media.py` — already fine

Already emits `@@dest=`, `@@action=`, `@@companion=` on stdout.
Called via direct import in pipeline, so `@@` lines don't go through subprocess.
No changes needed (pipeline emits these itself if needed).

## macOS app changes

### 7. New model: `DiffTableRow`

```swift
struct DiffTableRow: Identifiable {
    let id = UUID()
    let file: String
    var tagAction: String?        // "tagged" | "already_correct"
    var tagsAdded: String?        // comma-separated
    var originalTime: String?     // raw EXIF string
    var correctedTime: String?    // corrected EXIF string
    var timestampAction: String?  // "would_fix" | "no_change" | ...
    var timezone: String?
    var dest: String?             // from organize step
    var organizeAction: String?   // "would_move" | "moved" | ...
    var pipelineResult: String?   // "changed" | "unchanged" | "failed"
}
```

### 8. Parse `@@` lines in AppState

Add to `AppState`:

```swift
var diffTableRows: [DiffTableRow] = []
private var currentDiffRow: DiffTableRow?
```

In `appendLog(_ line: LogLine)`:
- If `line.stream == .stdout && line.text.hasPrefix("@@")`:
  parse key/value, accumulate into `currentDiffRow`.
  On `@@pipeline_file=`, start a new row.
  On `@@pipeline_result=`, finalize and append to `diffTableRows`.
- If `line.stream == .stderr`: append to `logOutput` as before.
- **Stop** appending `@@` stdout lines to `logOutput`.

### 9. New view: `DiffTableView`

A SwiftUI `Table` showing `diffTableRows` with columns:
- File (name)
- Original time (formatted)
- Corrected time (formatted)
- Timezone
- Destination (last path component)
- Status (color-coded: green=changed, grey=unchanged, red=failed)

Use the neon color palette for status indicators.

### 10. Replace log with table in WorkflowView

In `WorkflowView`, the right panel of `HSplitView` currently shows
`LogOutputView`.  Change to:

- **During/after dry-run**: show `DiffTableView` as primary, with a
  disclosure button to expand `LogOutputView` below it.
- **During/after apply**: show `DiffTableView` as primary (same layout).
- Log toggle button in execution bar still works, but now toggles the
  raw log beneath the table rather than the entire right panel.

### 11. Clear state

`clearLog()` also clears `diffTableRows` and `currentDiffRow`.

## Implementation order

1. **PR 1 — scripts: stdout/stderr cleanup + new `@@` lines**
   - [ ] step 1: fix tag-media.py stderr
   - [ ] step 2: add `@@` output to tag-media.py
   - [ ] step 3: fix fix-media-timestamp.py stderr, add `@@` output
   - [ ] step 4: update media-pipeline.py to separate streams and re-emit `@@`
   - [ ] tests for each script verifying `@@` lines in stdout

2. **PR 2 — macos: diff table view**
   - [ ] step 7: DiffTableRow model
   - [ ] step 8: AppState parsing
   - [ ] step 9: DiffTableView
   - [ ] step 10: WorkflowView integration
   - [ ] step 11: clear state

## Out of scope

- Per-file progress cards (apply mode) — separate task
- Timeline visualization — depends on this task's data
- Folder tree preview — removed from TODO
