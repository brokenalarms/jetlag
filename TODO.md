## `scripts/`

- (2026-02-24) **Replace conftest auto-skip with explicit decorators** — the source-inspection skip mechanism is opaque and misses indirect macOS dependencies. Replace with explicit `@pytest.mark.skipif` on each macOS-only class. Full plan: [todos/improve-platform-based-test-skipping.md](todos/improve-platform-based-test-skipping.md)

- (2026-02-20) **`tag-media.py` still makes a separate exiftool read for Make/Model** — `get_existing_exif_camera()` runs its own exiftool subprocess independent of any other data read for the file. For files where both EXIF and Finder tags need checking, this means 2 reads (tag list + exif) before deciding on writes. Low priority since these are already small reads, but could be merged if tag-media is ever extended to read more EXIF fields.

## `macos/`

- (2026-02-20) **`ScriptRunner` stream race condition** — `terminationHandler` calls `continuation.finish()` immediately when the process exits, but `readabilityHandler` callbacks may not have flushed all buffered data yet. Final lines of script output can be lost. Fix: drain both pipes explicitly before finishing the continuation (read until EOF on both file handles before calling `continuation.finish()`).

- (2026-02-24) **Timeline visualization** — Horizontal timeline view showing files as colored blocks per camera, positioned by timestamp. Two rows per camera: "before" (scattered, gaps from timezone errors) and "after" (correctly interleaved). Builds on diff table data. Use the neon color palette already defined in Assets (NeonCyan, NeonPink, NeonYellow, NeonPurple) to distinguish cameras.

- (2026-02-24) **Folder tree preview** — Collapsible tree view showing the destination folder structure that will be created during dry-run, with file counts per folder. Parse `@@dest=` paths into a tree model.

- (2026-02-24) **Pipeline steps visual redesign** — Render pipeline steps as a connected horizontal chain with a line behind them. Always-on steps (ingest, output) shown in green, non-toggleable. Optional steps (tag, fix-timestamp, gyroflow, archive-source) are toggleable. Enabling a task in the chain causes its configuration options to appear as grouped rows below (e.g. enabling archive-source reveals source action picker: leave/archive/delete, with yellow accent).

- (2026-02-24) **Timezone map in picker** — MapKit and CoreLocation are already linked in `project.yml` but unused. Replace or augment `TimezoneMapView` with an actual map showing timezone boundaries. When footage timezone differs from current system timezone, show both on the map with a visual arc.

## `scripts/` + `macos/`

- (2026-02-24) **Dry-run diff table** — During dry-run, replace raw log output with a structured table: file name, camera/profile, original timestamp, corrected timestamp, destination path. Color-code rows by camera profile.
   - `scripts/`: `fix-media-timestamp.py` needs to emit `@@original_time=` and `@@corrected_time=` in `@@` format alongside existing output
   - `macos/`: parse `@@` lines from `ScriptRunner` output into a `DiffTableView` model instead of `LogOutputView` text

- (2026-02-24) **Per-file progress cards** — During apply mode, replace scrolling logs with a card-based UI. Each file gets a card showing pipeline stages as checkmarks: Tagged → Timestamp Fixed → Organized → Gyroflow. Failed stages show red. Cards expand to show details.
   - `scripts/`: `media-pipeline.py` needs to emit `@@stage_complete=<stage>` after each step
   - `macos/`: card-based progress view consuming `@@stage_complete` events

## `web/`

(no open tasks)
