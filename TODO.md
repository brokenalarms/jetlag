# TODO — sliding context window

Read this at the start of each session. Pick ONE task and work on it.
Update this file at the end of the session. Completed work is recorded in commit messages — do not add a "Done" section here.

Tasks are grouped by subrepo. Cross-repo tasks appear under a combined heading — these need changes in multiple subrepos for a single valid PR.

---

## `scripts/`

- (2/20) **Performance baseline not yet recorded** — `tests/perf_baseline.json` does not exist yet. Run `pytest tests/test_performance.py -v -s` on the target macOS machine to generate it, then commit the file.

- (2/20) **`tag-media.py` still makes a separate exiftool read for Make/Model** — `get_existing_exif_camera()` runs its own exiftool subprocess independent of any other data read for the file. For files where both EXIF and Finder tags need checking, this means 2 reads (tag list + exif) before deciding on writes. Low priority since these are already small reads, but could be merged if tag-media is ever extended to read more EXIF fields.

## `macos/`

- (2/20) **`ScriptRunner` stream race condition** — `terminationHandler` calls `continuation.finish()` immediately when the process exits, but `readabilityHandler` callbacks may not have flushed all buffered data yet. Final lines of script output can be lost. Fix: drain both pipes explicitly before finishing the continuation (read until EOF on both file handles before calling `continuation.finish()`).

- (2/24) **Timeline visualization** — Horizontal timeline view showing files as colored blocks per camera, positioned by timestamp. Two rows per camera: "before" (scattered, gaps from timezone errors) and "after" (correctly interleaved). Builds on diff table data. Use the neon color palette already defined in Assets (NeonCyan, NeonPink, NeonYellow, NeonPurple) to distinguish cameras.

- (2/24) **Folder tree preview** — Collapsible tree view showing the destination folder structure that will be created during dry-run, with file counts per folder. Parse `@@dest=` paths into a tree model.

- (2/24) **Timezone map in picker** — MapKit and CoreLocation are already linked in `project.yml` but unused. Replace or augment `TimezoneMapView` with an actual map showing timezone boundaries. When footage timezone differs from current system timezone, show both on the map with a visual arc.

## `scripts/` + `macos/`

- (2/20) **`preserveSource` flag not passed to script** — `WorkflowView.runWorkflow()` binds a toggle to `state.preserveSource` but never adds a `--copy` / `--move` flag to the `import-media.sh` args. `import-media.py` doesn't currently expose this as a CLI flag — need to add it to the script first, then wire up in `WorkflowView`.

- (2/23) **Timezone suffix for group folder** — `--subfolder` / `folder_template` groundwork is done. Remaining:
   - `scripts/`: rename `--subfolder` → `--group` in `media-pipeline.py`; add `--group-timezone` flag (on by default) that appends timezone offset to group folder name, e.g. `Japan (+0900)`
   - `macos/`: rename the "Subfolder" field label to "Group"; add help text noting that date-range names (e.g. `05-06 Korea`) don't work well when backing up mid-trip since the end date isn't known yet; expose `--group-timezone` toggle
   - Tests: `--group Japan --timezone +0900` with `--group-timezone` → folder named `Japan (+0900)`; with `--no-group-timezone` → folder named `Japan`

- (2/24) **Dry-run diff table** — During dry-run, replace raw log output with a structured table: file name, camera/profile, original timestamp, corrected timestamp, destination path. Color-code rows by camera profile.
   - `scripts/`: `fix-media-timestamp.py` needs to emit `@@original_time=` and `@@corrected_time=` in `@@` format alongside existing output
   - `macos/`: parse `@@` lines from `ScriptRunner` output into a `DiffTableView` model instead of `LogOutputView` text

- (2/24) **Per-file progress cards** — During apply mode, replace scrolling logs with a card-based UI. Each file gets a card showing pipeline stages as checkmarks: Tagged → Timestamp Fixed → Organized → Gyroflow. Failed stages show red. Cards expand to show details.
   - `scripts/`: `media-pipeline.py` needs to emit `@@stage_complete=<stage>` after each step
   - `macos/`: card-based progress view consuming `@@stage_complete` events

## `web/`

(no open tasks)
