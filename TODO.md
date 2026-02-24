## `scripts/`

- (2026-02-24) **Replace conftest auto-skip with explicit decorators** — the source-inspection skip mechanism is opaque and misses indirect macOS dependencies. Replace with explicit `@pytest.mark.skipif` on each macOS-only class. Full plan: [todos/improve-platform-based-test-skipping.md](todos/improve-platform-based-test-skipping.md)

- (2026-02-20) **`tag-media.py` still makes a separate exiftool read for Make/Model** — `get_existing_exif_camera()` runs its own exiftool subprocess independent of any other data read for the file. For files where both EXIF and Finder tags need checking, this means 2 reads (tag list + exif) before deciding on writes. Low priority since these are already small reads, but could be merged if tag-media is ever extended to read more EXIF fields.
- (2026-02-24) make test output as quiet as possible, just 'running tests...' then the failed test name + FAILED (saves context)

## `macos/`

- (2026-02-20) **`ScriptRunner` stream race condition** — `terminationHandler` calls `continuation.finish()` immediately when the process exits, but `readabilityHandler` callbacks may not have flushed all buffered data yet. Final lines of script output can be lost. Fix: drain both pipes explicitly before finishing the continuation (read until EOF on both file handles before calling `continuation.finish()`).

- (2026-02-24) **Timeline visualization** — Horizontal timeline view showing files as colored blocks per camera, positioned by timestamp. Two rows per camera: "before" (scattered, gaps from timezone errors) and "after" (correctly interleaved). Builds on diff table data. Use the neon color palette already defined in Assets (NeonCyan, NeonPink, NeonYellow, NeonPurple) to distinguish cameras.

- (2026-02-24) **Folder tree preview** — Collapsible tree view showing the destination folder structure that will be created during dry-run, with file counts per folder. Parse `@@dest=` paths into a tree model.

- (2026-02-24) **Pipeline steps visual redesign** — Render pipeline steps as a connected horizontal chain with a line behind them. Always-on steps (ingest, output) shown in green, non-toggleable. Optional steps (tag, fix-timestamp, gyroflow, archive-source) are toggleable. Enabling a task in the chain causes its configuration options to appear as grouped rows below (e.g. enabling archive-source reveals source action picker: leave/archive/delete, with yellow accent).

- (2026-02-24) **Timezone map in picker** — MapKit and CoreLocation are already linked in `project.yml` but unused. Replace or augment `TimezoneMapView` with an actual map showing timezone boundaries. When footage timezone differs from current system timezone, show both on the map with a visual arc.

## `scripts/` + `macos/`

- (2026-02-24) **Media pipeline unification** — media-pipeline.py becomes the single entry point with always-on ingest/output and optional processing steps. Full spec: [todos/simplify-media-import.md](todos/simplify-media-import.md). Broken down into ordered PRs:

  1. **Extract `archive-source.py` from `import-media.py`** (`scripts/` only) — standalone subscript with leave/archive/delete modes. Extract archive rename logic from `import-media.py`, reuse `cleanup_empty_parent_dirs` from `lib/filesystem.py` for delete mode. New `test_archive_source.py` covering: leave no-op, archive rename, delete only passed files, empty dir cleanup, non-empty dir preservation, read-only source error, dry-run no-op.

  2. **`media-pipeline.py` core flow refactor** (`scripts/` only) — ingest step copies source → temp working dir (`tempfile.mkdtemp()`), output step always-on (remove `organize` from `--tasks`), `--source` reads from `source_dir` (no `import_dir` fallback — temp working dir replaces `import_dir` concept entirely). On success `os.rmdir()` the empty temp dir; on failure leave it as evidence. Update `test_media_pipeline.py` with ingest/output tests.

  3. **`media-pipeline.py` new features** (`scripts/` only) — `--copy-companion-files` flag copies companions through ingest → output (skipping optional processing steps), `--source-action` arg passed through to `archive-source.py` after all files processed, `--tasks` adds `archive-source` choice. Tests for companion copying and archive-source integration.

  4. **YAML + macOS app + docs** (`scripts/` + `macos/`) — remove `import_dir` from `media-profiles.yaml` (photo profiles: old `import_dir` value becomes `ready_dir`). `AppState.swift`: add `SourceAction` enum, rename `skipCompanion` → `copyCompanionFiles`, `PipelineStep` adds `.archiveSource` with `isAlwaysOn` for ingest/output. `WorkflowView.swift`: remove `hasImport` fork, always call `media-pipeline.sh`, build `--tasks` from optional steps only, always-on steps get distinct non-toggleable rendering. `ProfilesView.swift`: remove `import_dir` row. Swift tests: verify correct CLI args built for given UI state (test the interface boundary — never test script correctness from Swift). `docs/scripts.md`: update workflow design section.

  - **Testing boundary**: Python tests verify script behavior (filesystem effects). Swift tests verify the app builds correct CLI args for a given UI state — never run scripts or verify their effects.

- (2026-02-23) **Timezone suffix for group folder** — `--subfolder` / `folder_template` groundwork is done. Remaining:
   - `scripts/`: rename `--subfolder` → `--group` in `media-pipeline.py`; add `--group-timezone` flag (positive opt-in) that appends timezone offset to the group folder name, e.g. `Japan (+0900)` — requires `--group` and `--timezone` to also be set
   - `macos/`: rename the "Subfolder" field label to "Group"; add help text noting that date-range names (e.g. `05-06 Korea`) don't work well when backing up mid-trip since the end date isn't known yet; expose `--group-timezone` toggle
   - Tests: `--group Japan --timezone +0900 --group-timezone` → folder named `Japan (+0900)`; `--group Japan --timezone +0900` (without `--group-timezone`) → folder named `Japan`

- (2026-02-24) **Dry-run diff table** — During dry-run, replace raw log output with a structured table: file name, camera/profile, original timestamp, corrected timestamp, destination path. Color-code rows by camera profile.
   - `scripts/`: `fix-media-timestamp.py` needs to emit `@@original_time=` and `@@corrected_time=` in `@@` format alongside existing output
   - `macos/`: parse `@@` lines from `ScriptRunner` output into a `DiffTableView` model instead of `LogOutputView` text

- (2026-02-24) **Per-file progress cards** — During apply mode, replace scrolling logs with a card-based UI. Each file gets a card showing pipeline stages as checkmarks: Tagged → Timestamp Fixed → Organized → Gyroflow. Failed stages show red. Cards expand to show details.
   - `scripts/`: `media-pipeline.py` needs to emit `@@stage_complete=<stage>` after each step
   - `macos/`: card-based progress view consuming `@@stage_complete` events

## `web/`

(no open tasks)
