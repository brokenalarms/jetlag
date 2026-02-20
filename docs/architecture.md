# Architecture

## Layout

```
/                         ← repo root
├── scripts/              ← Python/shell scripts (work standalone, no knowledge of app)
│   ├── *.py / *.sh
│   ├── lib/              ← shared Python utilities
│   ├── media-profiles.yaml  ← shared config (used by both scripts and app)
│   └── tests/            ← script test suite (belongs with the scripts)
├── macos/                ← macOS SwiftUI app (sibling to scripts/, not nested inside)
│   ├── Sources/          ← Swift source files
│   └── project.yml       ← XcodeGen project spec
└── docs/                 ← documentation
```

`scripts/` and `macos/` are independent components that share `media-profiles.yaml`. The app reads config from and launches scripts in `scripts/`; the scripts have no knowledge of the app.

At build time, the `Bundle scripts` build phase copies `scripts/` into `Contents/Resources/scripts/` inside the app bundle. `AppState.scriptsDirectory` always points to this bundled copy.

---

## System overview

Two layers that share the same profile config:

1. **Python scripts** — CLI tools for timestamp fixing, tagging, organizing, gyroflow generation. Run standalone or via shell wrappers.
2. **Jetlag macOS app** (`macos/`) — SwiftUI wrapper that reads the same `media-profiles.yaml`, edits profiles, and launches the scripts via `ScriptRunner`.

---

## Script layer

### Hierarchy

```
base scripts (single file, explicit args, no profile knowledge)
  organize-by-date.py  fix-media-timestamp.py  tag-media.py  generate-gyroflow.py

batch wrappers (scan a dir, call base scripts in alpha order, pass args through)
  batch-organize-by-date.sh  batch-generate-gyroflow.py

orchestrators (read profiles, translate to base script args, run pipeline)
  media-pipeline.py   import-media.py
```

**Rule**: base scripts operate on a single file and know nothing about profiles. Orchestrators translate profile config into explicit args for base scripts. Batch wrappers are thin loops — they never swallow or reformat child output.

### Stdout / stderr split (machine-readable output)

Parent scripts need data from child scripts (e.g., the destination path after a file is moved). Protocol:

- Child writes **machine-readable data** to **stdout** with `@@` prefix: `@@dest=/path/to/file`, `@@action=moved`
- Child writes **human-readable messages** to **stderr** (passes through to the user's terminal)
- Parent captures stdout and parses `@@key=value` lines; stderr is never redirected (`2>&1` is never used on child scripts)

This keeps presentation decoupled from data. Never parse human-readable output — it could change without notice.

### Batch processing order

All batch operations process files in **alphabetical order**, completing all pipeline steps on one file before moving to the next. If interrupted, the pipeline resumes from the next unprocessed file without repeating steps.

### ExifTool usage per file

Exactly **one read call** then **one write call** maximum per file per script. Values from the read are cached in memory; all writes are accumulated and sent in a single exiftool invocation. Never call exiftool multiple times on the same file in a loop — it's slow.

Gotcha: exiftool fails silently if an `exiftool_tmp` directory exists alongside the target file (left over from a crashed run). `media-pipeline.py` checks for these at startup and prompts to delete them.

---

## Profile system (`media-profiles.yaml`)

Profiles are a YAML mapping where the **dict key is the profile name** — there is no `name` field inside a profile block. Example:

```yaml
profiles:
  gopro:
    file_extensions: [.mp4]
    tags: [gopro, action]
    exif:
      make: GoPro
      model: HERO12 Black
```

**`MediaProfile` (Swift)** has no `name` property. The profile name is always read from and written to the dict key. `ProfileService.load()` decodes the YAML into `[String: MediaProfile]` and the key is used wherever a name is needed. `ProfileService.write()` encodes back to the same structure — since `name` is not a field in the model, it never appears as a YAML key inside the profile block.

In `ProfilesView`, the name being edited is tracked as a separate `String` alongside the profile value: `editingProfile: (name: String, profile: MediaProfile)?`.

---

## Timestamp / EXIF model

### Source of truth hierarchy

1. **Filename** — `YYYYMMDD_HHMMSS` pattern in the filename is the highest priority source of truth. Never modify filenames.
2. **`DateTimeOriginal`** — contains local time + timezone offset. This is the source of truth for the shoot time. Never modify it unless `--overwrite-datetimeoriginal` is explicitly passed.
3. **QuickTime UTC fields** (`MediaCreateDate`, etc.) — integer fields that should store UTC. Our devices write real UTC here. Interpret as UTC and verify by cross-checking against `DateTimeOriginal + timezone`.
4. **File birth time** — set via `setfile -d`. FCP uses this as the fallback for "Content Created" on import.

### What FCP reads

- **Import screen** ("Content Created"): reads file birth time.
- **After import** (`Keys:CreationDate`): FCP converts the stored timezone to UTC, then displays in the system timezone. A value of `08:07:22+08:00` is stored, converted to `00:07:22 UTC`, displayed as `09:07:22` in Japan (+09:00).
- iPhone records `Keys:CreationDate` with timezone — this should match `DateTimeOriginal`.
- Modification time is **not set** by these scripts (it naturally reflects when the file was last written, e.g. by exiftool).

### QuickTime UTC note

From ExifTool docs: integer QuickTime date/time fields should be UTC but cameras often store local time instead. Our devices write real UTC. Do not use the ExifTool `QuickTimeUTC` API flag — handle the UTC interpretation explicitly in the scripts.

### Camera quirks

**GoPro / FAT filesystem**: FAT stores modification time in the camera's local timezone with no TZ info. If the camera is set to +02:00 but the Mac is +09:00, birth/mod times will be 7 hours off. `MediaCreateDate` is UTC and correct. A ~7-hour (or other non-standard) offset in birth vs EXIF time indicates camera TZ mismatch, not a bug.

**macOS SD card copy**: birth time is often preserved from the source FAT filesystem rather than reset to the copy time. This propagates the camera's wrong-TZ birth time to the Mac. The timestamp fix scripts correct this.

---

## macOS app (`macos/`)

### State management

`AppState` (`@Observable`) holds all workflow and profile state. Views bind directly to it. No view models — state is lifted to `AppState` rather than scattered across views.

Key state:
- `profilesConfig: ProfilesConfig?` — decoded YAML, including the `[String: MediaProfile]` profiles dict
- `selectedProfile: String` — the dict key of the active profile
- `enabledSteps: Set<PipelineStep>` — which pipeline steps are toggled on
- `isRunning`, `logOutput`, `currentProcess` — execution state

### ProfileService

Two static methods:
- `load(from:)` — decodes YAML into `ProfilesConfig` using Yams. Throws `ProfileLoadError` with structured fields for display.
- `write(_:to:)` — encodes `ProfilesConfig` back to YAML using Yams. Because `MediaProfile.CodingKeys` excludes `name`, the profile name is only ever the dict key.

### ScriptRunner

Launches a bash script as a `Process`, attaches `Pipe`s to stdout and stderr, and vends an `AsyncStream<LogLine>`. Each line is tagged `.stdout` or `.stderr`. Machine-readable `@@key=value` lines are filtered via `LogLine.isMachineReadable` — the UI only displays non-machine-readable lines.

**Known gotcha** (TODO): `terminationHandler` calls `continuation.finish()` immediately when the process exits, but `readabilityHandler` callbacks may not have flushed all buffered output yet. The last few lines of a script can be silently dropped. Fix: drain both pipes to EOF before finishing the continuation.

### WorkflowView → scripts

`runWorkflow()` selects either `import-media.sh` or `media-pipeline.sh` depending on whether the Import step is enabled, then builds args from `AppState`:

- `--profile` — always passed
- `--group` (from `subfolder` field)
- `--tasks tag fix-timestamp organize gyroflow` — only steps that are enabled in `enabledSteps`, mapped from `PipelineStep` to the string names that `media-pipeline.py` accepts. Passed only for `media-pipeline.sh` (not import).
- `--timezone` — when Fix Timezone step is enabled and a timezone is set
- `--apply` — when apply mode is on

`updateEnabledSteps()` is called on profile change. It **intersects** the current `enabledSteps` with the new profile's available steps — removing steps that the new profile doesn't support while preserving the user's toggle state for steps that remain available. (A union would always reset to all-enabled.)

### ProfilesView

Profile editing tracks name separately from the model: `editingProfile: (name: String, profile: MediaProfile)?`. `ProfileEditorView` takes both `profileName: String` (editable) and `profile: MediaProfile` as separate `@State` values, and calls `onSave(name, profile)` — the caller then writes `profiles[name] = profile` to the config dict directly.

---

## Testing

Tests live in `scripts/tests/`. Run via `scripts/run-tests.py`.

- **Regression tests** (`test_fix_media_timestamp.py` etc.) — assert actual file state before and after, not just exit codes or stdout. Structured as "record before → run script → compare after" with human-readable expected vs actual diffs.
- **Performance tests** (`test_performance.py`) — snapshot harness. Measures median wall-clock time over 3 runs per script, compares to a saved baseline (`scripts/tests/perf_baseline.json`). Threshold: **5% slower than baseline = regression**. Delete `perf_baseline.json` to re-record after intentional perf improvements.

Testing rules:
- Testing `returncode == 0` is not testing behavior — it only confirms the script didn't crash.
- Tests should not be updated without explicit confirmation unless following TDD (break test first, confirm expected failure, then update).
