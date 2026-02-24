# Spec: Unify media pipeline as single orchestrator

## Problem

The app forks between import-media.sh and media-pipeline.sh depending on which steps are enabled. The two scripts have incompatible args (--group vs --subfolder). Import dir is an implementation detail exposed to the user unnecessarily.

## Design

media-pipeline.py becomes the single entry point. The pipeline has a fixed frame — **ingest** and **output** always run — with optional processing steps in between.

### Pipeline

```
INGEST (always) → [tag] → [fix-timestamp] → OUTPUT (always) → [gyroflow] → [archive-source]
```

**Ingest** and **output** are structural steps that always execute. **Tag**, **fix-timestamp**, **gyroflow**, and **archive-source** are optional processing steps controlled by `--tasks`.

### Per-file flow

For each file matching profile `file_extensions` in `--source`:

1. **Ingest**: copy file from source to temp working dir (flat, no subdirectories)
2. **Tag** (if in `--tasks`): apply Finder tags + EXIF metadata to the copy in working dir
3. **Fix-timestamp** (if in `--tasks`): correct timestamps on the copy in working dir
4. **Output**: move processed copy from working dir to `ready_dir` via organize-by-date (date-based folder structure using `--subfolder` template)
5. **Gyroflow** (if in `--tasks`): generate stabilization project on the file now in `ready_dir`
6. **Archive-source** (if in `--tasks`): after all files are processed, act on the source folder as a whole. Calls `archive-source.py` subscript. See [archive-source behavior](#archive-source-behavior).

### Directory roles

| Role | Source | Lifetime |
|---|---|---|
| **source** | `--source` or profile `source_dir` | Read-only during pipeline. Archive renames whole folder; delete removes only processed files + companions then cleans empty dirs. |
| **working** | `tempfile.mkdtemp()` | Created per-run, cleaned up after. Internal, not user-facing. |
| **ready** | profile `ready_dir` or `--target` | User-facing output. Watched folder for backup sync — files only land here when fully processed. |
| **archive** | Sibling of source: `<source> - archived <date>` | Only exists when archive-source task runs with `--action archive`. Whole source folder renamed. |

Memory card and local directory sources are treated identically — both are read-only inputs to the pipeline.

### Archive-source behavior

`archive-source` is an optional task backed by `archive-source.py`. It runs after all files have been processed. The pipeline passes it the list of processed files (and their companions). If the task is not in `--tasks`, the source is left untouched (no script called).

**`--action archive`** (default)
- Rename source folder: `<source>` → `<source> - archived <YYYY-MM-DD>`
- One operation on the whole folder — companions, subdirectories, everything comes along.
- Good for: memory cards where you want a clear "done" marker, any source where you want a record of what was imported.

**`--action delete`**
- Delete processed files and their companions from the source folder.
- After deletions, walk up from each file's parent to the source root, removing any now-empty directories.
- Does NOT `rmtree` the source folder — only files the pipeline actually processed (plus companions) are removed. Other files in the source folder are left alone.
- Good for: local copies where the source is already a duplicate and you want to reclaim space without nuking unrelated files.

**Common behavior:**
- Runs only after all per-file pipeline steps succeed. If the pipeline is interrupted before archive-source runs, source is untouched and a re-run reprocesses everything.
- Archive mode operates on the whole folder. Delete mode operates per-file (processed files + companions only), then cleans up empty dirs.
- If source is read-only (SD card write-protect, permissions): log `"Read-only source, couldn't <action>: <source>"` and exit non-zero.

### Companion files

Companion files (`.lrv`, `.thm`, `.srt`, etc. from profile `companion_extensions`) are camera artifacts that don't need processing but may be useful at the destination.

**Source**: archive mode renames the whole folder so companions come along implicitly. Delete mode explicitly removes companions alongside their main files (the pipeline passes the file list to archive-source).

**Destination**: controlled by `--copy-companion-files` (default: off).
- When off: companions are not copied to working dir or output to ready_dir.
- When on: companions are copied to working dir and output to ready_dir alongside their main file (but skip optional processing steps — no tagging, timestamping, or gyroflow).

Good for: `.srt` subtitle files from Insta360 or DJI that you want alongside the video in ready_dir but don't want promoted to full `file_extensions` (which would tag/timestamp them).

If a companion extension needs full processing (tagging, timestamping), it should be in `file_extensions` instead — then it goes through the complete pipeline like any other file.

### CLI args for media-pipeline.py

**Modified:**
- `--source` — where files originate (SD card or local dir). Overrides profile `source_dir`. Required unless profile provides `source_dir`.
- `--target` — output directory. Overrides profile `ready_dir`. Required unless profile provides `ready_dir`.
- `--tasks` — optional processing steps: `tag`, `fix-timestamp`, `gyroflow`, `archive-source`. Default: all except `archive-source`. Ingest and output always run regardless.

**New:**
- `--source-action` — always passed through to `archive-source.py`: `leave` (default, no-op), `archive` (rename folder), or `delete` (remove folder).
- `--copy-companion-files` — also copy companion files (matching profile `companion_extensions`) to ready_dir. Default: off. Companions skip optional processing steps (tag, fix-timestamp, gyroflow).

**Unchanged:**
- `--profile`, `--subfolder`, `--timezone`, `--location`, `--apply`, `--verbose`

## Changes by file

### scripts/media-pipeline.py

- Add `copy_to_working_dir(source_file, working_dir)` function — flat `shutil.copy2()`
- Add `--source-action` and `--copy-companion-files` args
- Update `--tasks` choices: remove `"organize"` (output is always on). Choices become `["tag", "fix-timestamp", "gyroflow", "archive-source"]`. Default: all except `archive-source`.
- In `main()`:
  - Always create temp working dir via `tempfile.mkdtemp()`
  - Scan `--source` (or profile `source_dir`) for files matching `file_extensions`
  - Resolve `ready_dir` from profile `ready_dir` or `--target`
  - Clean up temp working dir after all files processed
  - If `archive-source` in `--tasks`: call `archive-source.py` with `--source`, `--action`, and `--files` (list of processed files + their companions) after all files processed
- In `process_file()`:
  - Step 0 (ingest): copy source file to working dir (always)
  - Steps 1-2 (tag, fix-timestamp): operate on working dir copy (unchanged logic, now conditional on `--tasks`)
  - Step 3 (output): organize working dir copy to ready_dir (always, not conditional on tasks)
  - Step 4 (gyroflow): unchanged (operates on file in ready_dir)
  - When `--copy-companion-files`: for each main file, also ingest → output its companion files immediately after the main file's output step (before gyroflow). Companions skip optional processing (tag, fix-timestamp, gyroflow). Per-file, not batched — if interrupted, companions for completed files are already in ready_dir.
- `--source` default changes from profile `import_dir` → profile `source_dir`

### scripts/archive-source.py ~~(new)~~ ✓ done

Standalone subscript. Called by media-pipeline.py when `archive-source` is in `--tasks`. Also runnable independently.

- `--source` — source directory to act on (required)
- `--action` — `leave` (default, no-op), `archive`, or `delete`
- `--files` — file paths to delete (required for `delete`, ignored for `archive`/`leave`). Accepts multiple paths. The pipeline passes processed files + their companions.
- `--apply` / `--verbose` — same dry-run semantics as other subscripts
- Archive mode: `os.rename(source, f"{source} - archived {date}")`
- Delete mode: remove each file in `--files`, then walk up from each file's parent dir to `--source`, calling `os.rmdir()` on empty directories (stops at `--source` itself — does not delete the source root unless it's empty too)
- Read-only fallback: log error, exit non-zero

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
- Add `sourceAction: SourceAction` (default `.leave`)
- Rename `skipCompanion: Bool` → `copyCompanionFiles: Bool` (default `false`) — controls whether companions are also copied to ready_dir
- `PipelineStep`: add `.archiveSource` case; add computed property `isAlwaysOn` — true for `.importFromCard` and `.organize`
- Update `.importFromCard` help text: `"Copy files from source to working directory for processing"`
- Update `.organize` help text: `"Move processed files into date-based folders in ready directory"`
- `availableSteps`: unchanged (still returns all steps including import and organize)
- `enabledSteps`: always-on steps cannot be removed from the set

### macos/Sources/Views/WorkflowView.swift

- `stepsPipeline`: render always-on steps (`isAlwaysOn`) with distinct visual treatment — non-toggleable, visually differentiated from optional steps (different background, no checkbox, or structural separator)
- Always call `media-pipeline.sh` (remove the `hasImport ? "import-media.sh" : "media-pipeline.sh"` fork)
- Always pass `--source` with `state.sourceDir`
- Build `--tasks` from enabled optional steps only (exclude `.importFromCard` and `.organize`). `.archiveSource` maps to task name `archive-source`.
- Always pass `--source-action` with value from `state.sourceAction` (`leave`, `archive`, or `delete`)
- Pass `--copy-companion-files` when `state.copyCompanionFiles`
- `importCardOptions` section: always visible when profile selected (not gated on `.importFromCard` enabled, since import is always on). Rename GroupBox label from "Memory Card / Source Actions" to "Source"
- Show `sourceAction` picker (leave / archive / delete). "Delete" option shows caution text: `"Deletes processed files and companions from source after successful processing"`
- `pipelineTaskNames`: remove `.organize` mapping (no longer a task choice). Add `.archiveSource` → `"archive-source"`. Keep `.tag`, `.fixTimezone`, `.gyroflow`. Do not add `.importFromCard` (not a task choice).
- `countMediaFiles()`: always count from `state.sourceDir` (remove the `hasImport ?` branch)

### macos/Sources/Views/ProfilesView.swift

- Remove `import_dir` row from profile editor
- Keep `ready_dir` as "Ready dir" (all profile types)

### scripts/tests/test_media_pipeline.py (new)

- Test ingest: file copied from source to temp working dir
- Test full pipeline: ingest → tag → output flow, verify file ends up in ready_dir with correct tags
- Test copy-companion-files: companions copied to ready_dir when flag is on
- Test pipeline without archive-source: source folder untouched after processing

### scripts/tests/test_archive_source.py ~~(new)~~ ✓ done

- Test leave: source folder and files untouched (no-op)
- Test archive: source folder renamed to `<source> - archived <date>`
- Test delete: only files passed via `--files` are removed; other files in source survive
- Test delete cleans empty dirs: after deleting files, empty parent dirs up to source root are removed
- Test delete preserves non-empty dirs: parent dirs containing other files are not removed
- Test read-only source: logs error, exits non-zero
- Test dry-run: no changes when `--apply` not passed

### docs/scripts.md

- Update workflow design section to reflect single-orchestrator model

### TODO.md

- Remove completed task (this one)
- Add deferred task: rename `--subfolder` → `--group` across scripts and app

## Deprecations

- **scripts/import-media.py** — superseded by media-pipeline.py with always-on ingest. No changes needed now; remove in a future cleanup.
- **`import_dir` in profiles** — replaced by temp working dir. Removed from YAML and profile editor.

## No changes to

- scripts/organize-by-date.py — called by media-pipeline.py as today (future: add y/n/a confirmation)
- scripts/tag-media.py, scripts/fix-media-timestamp.py — called as today
- scripts/generate-gyroflow.py — called as today
- scripts/import-media.sh — stays but unused by app (import-media.py is deprecated, not deleted)
