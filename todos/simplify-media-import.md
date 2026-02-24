# Spec: Unify media pipeline as single orchestrator

## Problem

The app forks between import-media.sh and media-pipeline.sh depending on which steps are enabled. The two scripts have incompatible args (--group vs --subfolder). Import dir is an implementation detail exposed to the user unnecessarily.

## Design

media-pipeline.py becomes the single entry point. The app always calls it with --tasks.

Tasks (per-file, in order):
1. **import** — flat copy from --source to import_dir (working dir), preserving source structure
2. **tag** — apply Finder tags + EXIF from profile
3. **fix-timestamp** — correct timestamps
4. **organize** — organize by date into ready_dir
5. **gyroflow** — generate stabilization projects

Directory roles:
- **source_dir** — SD card (from profile + --source override)
- **import_dir** — working dir. Read from YAML if set; if absent, script creates a `tempfile.mkdtemp()` and cleans it up after
- **ready_dir** — user-facing output dir

New CLI args for media-pipeline.py:
- `--tasks` gains "import" as a valid choice
- `--source` — SD card path for import step (required when import is in tasks)
- `--skip-companion` — skip companion files during import

When import is in tasks: files are discovered from --source, copied to working dir, then processed through remaining steps. When import is not in tasks: files are discovered from import_dir (working dir) as today.

## Changes by file

### scripts/media-pipeline.py
- Add `import_file()` function (flat copy to working dir)
- Add "import" to --tasks choices
- Add --source and --skip-companion args
- In `main()`: if import in tasks, scan --source for files; otherwise scan import_dir. If import_dir not in profile, use `tempfile.mkdtemp()`
- In `process_file()`: add Step 0 (import) before existing steps. After import, subsequent steps operate on the copy in working dir
- Temp dir cleanup on completion

### scripts/media-profiles.yaml
- Photo profiles (dji-mini-4-pro-photo, sony-a7iv-photo): current import_dir becomes ready_dir, import_dir removed
- Video profiles: unchanged (they already have both import_dir and ready_dir)

### macos/Sources/Views/WorkflowView.swift
- Always call media-pipeline.sh (remove the `hasImport ? "import-media.sh" : "media-pipeline.sh"` fork)
- Always pass --tasks with the enabled pipeline steps
- Pass --source when import step is enabled
- Pass --skip-companion when toggled

### macos/Sources/Views/ProfilesView.swift
- Remove import_dir row from profile editor
- Keep ready_dir as "Ready dir" (all profile types)

### macos/Sources/Models/AppState.swift
- Update `PipelineStep.importFromCard.help` text
- `pipelineTaskNames` mapping: `.importFromCard` → `"import"`

### scripts/tests/test_media_pipeline.py (new)
- Test import task: files copied from source to working dir
- Test import task with temp dir fallback (no import_dir in profile)
- Test full pipeline: import → tag → organize flow
- Test without import task: files read from import_dir as before

### docs/scripts.md
- Update workflow design section

### TODO.md
- Add deferred task: rename import_dir → working_dir in YAML and scripts

## No changes to
- scripts/import-media.py — stays as standalone CLI tool (already has flat copy from first commit)
- scripts/organize-by-date.py, scripts/tag-media.py, etc. — unchanged
