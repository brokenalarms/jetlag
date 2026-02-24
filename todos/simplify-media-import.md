# Spec: Unify media pipeline as single orchestrator

## Problem

The app forks between import-media.sh and media-pipeline.sh depending on which steps are enabled. The two scripts have incompatible args (--group vs --subfolder). Import dir is an implementation detail exposed to the user unnecessarily.

## Design

media-pipeline.py becomes the single entry point. The pipeline has a fixed frame — **ingest** and **output** always run — with optional processing steps in between.

### Pipeline

```
INGEST (always) → [tag] → [fix-timestamp] → OUTPUT (always) → [gyroflow] → [source-action]
```

**Ingest** and **output** are structural steps that always execute. **Tag**, **fix-timestamp**, and **gyroflow** are optional processing steps controlled by `--tasks`. **Source-action** is controlled by `--source-action`.

### Per-file flow

For each file matching profile `file_extensions` in `--source`:

1. **Ingest**: copy file from source to temp working dir (flat, no subdirectories)
2. **Tag** (if in `--tasks`): apply Finder tags + EXIF metadata to the copy in working dir
3. **Fix-timestamp** (if in `--tasks`): correct timestamps on the copy in working dir
4. **Output**: move processed copy from working dir to `ready_dir` via organize-by-date (date-based folder structure using `--subfolder` template)
5. **Gyroflow** (if in `--tasks`): generate stabilization project on the file now in `ready_dir`
6. **Source-action** (per `--source-action`):
   - `leave` (default): source file untouched
   - `archive`: move original source file (and companions) to archive folder
   - `delete`: delete original source file (and companions)

All three modes are per-file (after successful processing), so all give resumability — only successfully-processed files are affected. If the script is interrupted, unprocessed files remain in source. Re-running picks up where it left off.

### Directory roles

| Role | Source | Lifetime |
|---|---|---|
| **source** | `--source` or profile `source_dir` | Never modified in-place. Post-processing fate controlled by `--source-action`. |
| **working** | `tempfile.mkdtemp()` | Created per-run, cleaned up after. Internal, not user-facing. |
| **ready** | profile `ready_dir` or `--target` | User-facing output. Watched folder for backup sync — files only land here when fully processed. |
| **archive** | Sibling of source: `<source> - archived <date>` | Only exists when `--source-action archive`. Marks processed source files. Created on first successful archive. |

Memory card and local directory sources are treated identically — both are read-only inputs to the pipeline.

### Source-action behavior

`--source-action` controls what happens to each source file after successful processing. Three modes:

**`leave`** (default)
- Source file untouched. Safest option.
- Good for: memory cards (eject manually), precious originals, dry-run exploration.

**`archive`**
- Per-file move to archive folder: `<source_basename> - archived <YYYY-MM-DD>`, created as sibling of `--source` dir on first successful archive.
- Preserves directory structure within archive relative to source root.
- Good for: memory cards where you want a record of what was imported, any source where you want resumability with a clear "done" marker.

**`delete`**
- Per-file delete (`os.remove()`) after successful processing.
- No archive folder, no clutter.
- Good for: local copies where the source is already a duplicate and you want to reclaim space.

**Common behavior across all modes:**
- Action is per-file, taken only after that file's full pipeline completes. Provides resumability — unprocessed files remain in source.
- Companion files (matching profile `companion_extensions`) are always included in the source-action alongside their main file. No toggle — you'd never archive/delete a main file and leave its `.lrv`/`.thm` orphaned.
- If source is read-only (SD card write-protect, permissions): log `"Read-only source, couldn't <action>: <filename>"` and continue. Non-fatal.

### Companion files

Companion files (`.lrv`, `.thm`, `.srt`, etc. from profile `companion_extensions`) are camera artifacts that don't need processing but may be useful at the destination.

**Source-action**: companions are always included. When the main file is archived or deleted, its companions are too. No toggle — orphaning companions in source would never be useful.

**Destination**: controlled by `--include-companions` (default: off).
- When off: companions are not copied to working dir or output to ready_dir. They only participate in source-action.
- When on: companions are copied to working dir and output to ready_dir alongside their main file (but skip optional processing steps — no tagging, timestamping, or gyroflow).

Good for: `.srt` subtitle files from Insta360 or DJI that you want alongside the video in ready_dir but don't want promoted to full `file_extensions` (which would tag/timestamp them).

If a companion extension needs full processing (tagging, timestamping), it should be in `file_extensions` instead — then it goes through the complete pipeline like any other file.

### CLI args for media-pipeline.py

**Modified:**
- `--source` — where files originate (SD card or local dir). Overrides profile `source_dir`. Required unless profile provides `source_dir`.
- `--target` — output directory. Overrides profile `ready_dir`. Required unless profile provides `ready_dir`.
- `--tasks` — optional processing steps: `tag`, `fix-timestamp`, `gyroflow`. Default: all. Ingest and output always run regardless.

**New:**
- `--source-action` — what to do with each source file after successful processing: `leave` (default), `archive`, `delete`. Companions always follow the main file.
- `--include-companions` — also copy companion files (matching profile `companion_extensions`) to ready_dir. Default: off. Companions skip optional processing steps (tag, fix-timestamp, gyroflow).

**Unchanged:**
- `--profile`, `--subfolder`, `--timezone`, `--location`, `--apply`, `--verbose`

## Changes by file

### scripts/media-pipeline.py

- Add `copy_to_working_dir(source_file, working_dir)` function — flat `shutil.copy2()`
- Add `handle_source_action(source_file, source_dir, action, archive_dir)` function — per-file leave/archive/delete with read-only fallback (log + continue)
- Add `--source-action` and `--include-companions` args
- Update `--tasks` choices: remove `"organize"` (output is always on). Choices become `["tag", "fix-timestamp", "gyroflow"]`
- In `main()`:
  - Always create temp working dir via `tempfile.mkdtemp()`
  - Scan `--source` (or profile `source_dir`) for files matching `file_extensions`
  - Resolve `ready_dir` from profile `ready_dir` or `--target`
  - Create archive dir on first successful archive (if `--source-action archive`)
  - Clean up temp working dir after all files processed
- In `process_file()`:
  - Step 0 (ingest): copy source file to working dir (always)
  - Steps 1-2 (tag, fix-timestamp): operate on working dir copy (unchanged logic, now conditional on `--tasks`)
  - Step 3 (output): organize working dir copy to ready_dir (always, not conditional on tasks)
  - Step 4 (gyroflow): unchanged (operates on file in ready_dir)
  - Step 5 (source-action): leave, archive, or delete source file + companions (per `--source-action`, companions always included)
  - When `--include-companions`: also run ingest → output for each companion file (skip tag, fix-timestamp, gyroflow)
- `--source` default changes from profile `import_dir` → profile `source_dir`

### scripts/media-profiles.yaml

All profiles: remove `import_dir` (working dir is now always temp).

Photo profiles (dji-mini-4-pro-photo, sony-a7iv-photo, sony-a7v-photo):
- Current `import_dir` value becomes `ready_dir`
- e.g., `import_dir: /Volumes/Extreme GRN/Photos/Import` → `ready_dir: /Volumes/Extreme GRN/Photos/Import`

Video profiles (insta360, gopro, dji-mini-4-pro-video, sony-a7iv-video, sony-a7v-video, iphone-16-pro):
- Remove `import_dir` line
- `ready_dir` unchanged

### macos/Sources/Models/AppState.swift

- Add `SourceAction` enum: `.leave`, `.archive`, `.delete` with raw string values matching CLI args
- Replace `preserveSource: Bool` with `sourceAction: SourceAction` (default `.leave`)
- Rename `skipCompanion: Bool` → `includeCompanions: Bool` (default `false`) — controls whether companions are also copied to ready_dir
- `PipelineStep`: add computed property `isAlwaysOn` — true for `.importFromCard` and `.organize`
- Update `.importFromCard` help text: `"Copy files from source to working directory for processing"`
- Update `.organize` help text: `"Move processed files into date-based folders in ready directory"`
- `availableSteps`: unchanged (still returns all steps including import and organize)
- `enabledSteps`: always-on steps cannot be removed from the set

### macos/Sources/Views/WorkflowView.swift

- `stepsPipeline`: render always-on steps (`isAlwaysOn`) with distinct visual treatment — non-toggleable, visually differentiated from optional steps (different background, no checkbox, or structural separator)
- Always call `media-pipeline.sh` (remove the `hasImport ? "import-media.sh" : "media-pipeline.sh"` fork)
- Always pass `--source` with `state.sourceDir`
- Build `--tasks` from enabled optional steps only (exclude `.importFromCard` and `.organize`)
- Pass `--source-action` with value from `state.sourceAction` (`leave`, `archive`, or `delete`)
- Pass `--include-companions` when `state.includeCompanions`
- `importCardOptions` section: always visible when profile selected (not gated on `.importFromCard` enabled, since import is always on). Rename GroupBox label from "Memory Card / Source Actions" to "Source"
- Replace `preserveSource` toggle with `sourceAction` picker (leave / archive / delete). "Delete" option shows caution text: `"Permanently deletes source files after successful processing"`
- `pipelineTaskNames`: remove `.organize` mapping (no longer a task choice). Keep `.tag`, `.fixTimezone`, `.gyroflow`. Do not add `.importFromCard` (not a task choice).
- `countMediaFiles()`: always count from `state.sourceDir` (remove the `hasImport ?` branch)

### macos/Sources/Views/ProfilesView.swift

- Remove `import_dir` row from profile editor
- Keep `ready_dir` as "Ready dir" (all profile types)

### scripts/tests/test_media_pipeline.py (new)

- Test ingest: file copied from source to temp working dir
- Test full pipeline: ingest → tag → output flow, verify file ends up in ready_dir with correct tags
- Test source-action leave: source file untouched after processing
- Test source-action archive: source file moved to archive folder after processing
- Test source-action delete: source file deleted after processing
- Test source-action with read-only source: logs warning, continues without error
- Test include-companions: companions copied to ready_dir when flag is on
- Test companions always follow source-action: archive/delete main file also archives/deletes companions (no flag needed)
- Test resumability: pre-existing archive folder with some files, re-run processes only unarchived source files

### docs/scripts.md

- Update workflow design section to reflect single-orchestrator model

### TODO.md

- Remove completed task (this one)
- Add deferred task: rename `--subfolder` → `--group` across scripts and app

## Deprecations

- **scripts/import-media.py** — superseded by media-pipeline.py with always-on ingest. No changes needed now; remove in a future cleanup.
- **`import_dir` in profiles** — replaced by temp working dir. Removed from YAML and profile editor.

## No changes to

- scripts/organize-by-date.py — called by media-pipeline.py as today
- scripts/tag-media.py, scripts/fix-media-timestamp.py — called as today
- scripts/generate-gyroflow.py — called as today
- scripts/import-media.sh — stays but unused by app (import-media.py is deprecated, not deleted)
