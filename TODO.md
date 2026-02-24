# TODO — sliding context window

Read this at the start of each session. Pick ONE task and work on it.
Update this file at the end of the session. Completed work is recorded in commit messages — do not add a "Done" section here.

---

## Open tasks (pick ONE)

### Jetlag app

1. **`preserveSource` flag not passed to script** — `WorkflowView.runWorkflow()` binds a toggle to `state.preserveSource` but never adds a `--copy` / `--move` flag to the `import-media.sh` args. `import-media.py` doesn't currently expose this as a CLI flag — need to add it to the script first, then wire up in `WorkflowView`.

2. **`ScriptRunner` stream race condition** — `terminationHandler` calls `continuation.finish()` immediately when the process exits, but `readabilityHandler` callbacks may not have flushed all buffered data yet. Final lines of script output can be lost. Fix: drain both pipes explicitly before finishing the continuation (read until EOF on both file handles before calling `continuation.finish()`).

3. ~~**Scripts not bundled for release builds**~~ — `project.yml` `postBuildScripts` copies `scripts/` for all configurations; `AppState` uses `Bundle.main.resourcePath` unconditionally. Not a live issue.

5. **Timezone suffix for group folder** — `--subfolder` / `folder_template` groundwork is done. Remaining:
   - Rename `--subfolder` → `--group` in `media-pipeline.py` and app (group is the right semantic — it groups files by shooting location/timezone)
   - Add `--group-timezone` flag to `media-pipeline.py` (on by default): when set, appends the timezone offset to the group folder name, e.g. `Japan (+0900)`. App should expose a toggle so users can opt out.
   - App: rename the "Subfolder" field label to "Group"; add help text noting that date-range names (e.g. `05-06 Korea`) don't work well when backing up mid-trip since the end date isn't known yet
   - Tests: `--group Japan --timezone +0900` with `--group-timezone` → folder named `Japan (+0900)`; with `--no-group-timezone` → folder named `Japan`

### App UI — visual preview & feedback

The app currently wraps the scripts with a config GUI and scrolling log output. These tasks add visual representations that make the value proposition tangible — "Every camera. One timeline." should be something you *see*, not just read in log lines.

The `@@key=value` protocol already emits structured data (dest paths, actions, timezones). These tasks parse that data into visual components instead of displaying it as text.

6. **Dry-run diff table** — During dry-run, replace raw log output with a structured table: file name, camera/profile, original timestamp, corrected timestamp, destination path. Color-code rows by camera profile. This is the practical first step — makes dry-run a genuine preview instead of "safe mode with the same output." Script-side: `fix-media-timestamp.py` needs to emit `@@original_time=` and `@@corrected_time=` in `@@` format alongside existing output. App-side: parse `@@` lines from `ScriptRunner` output into a `DiffTableView` model instead of `LogOutputView` text.

7. **Timeline visualization** — Horizontal timeline view showing files as colored blocks per camera, positioned by timestamp. Two rows per camera: "before" (scattered, gaps from timezone errors) and "after" (correctly interleaved). This is the visual payoff of "cameras lie about time" → "footage lands in the right place." Builds on the diff table data (task 6). Use the neon color palette already defined in Assets (NeonCyan, NeonPink, NeonYellow, NeonPurple) to distinguish cameras.

8. **Per-file progress cards** — During apply mode, replace scrolling logs with a card-based UI. Each file gets a card showing pipeline stages as checkmarks: Tagged → Timestamp Fixed → Organized → Gyroflow. Failed stages show red. Cards expand to show details. Gives visual progress feedback and makes failures immediately obvious rather than buried in log text. Requires `@@stage_complete=<stage>` output from `media-pipeline.py`.

9. **Folder tree preview** — Collapsible tree view showing the destination folder structure that will be created during dry-run, with file counts per folder. Parse `@@dest=` paths into a tree model. Shows the organizational outcome ("Smart date-based organization") before anything moves.

10. **Timezone map in picker** — MapKit and CoreLocation are already linked in `project.yml` but unused. Replace or augment `TimezoneMapView` with an actual map showing timezone boundaries. When footage timezone differs from current system timezone, show both on the map with a visual arc. Reinforces the "jetlag" brand and the travel-filmmaker identity.

### Scripts

11. **Performance baseline not yet recorded** — `tests/perf_baseline.json` does not exist yet. Run `pytest tests/test_performance.py -v -s` on the target macOS machine to generate it, then commit the file.

12. **`tag-media.py` still makes a separate exiftool read for Make/Model** — `get_existing_exif_camera()` runs its own exiftool subprocess independent of any other data read for the file. For files where both EXIF and Finder tags need checking, this means 2 reads (tag list + exif) before deciding on writes. Low priority since these are already small reads, but could be merged if tag-media is ever extended to read more EXIF fields.

### Web

(no open tasks)

---

## Architecture reminders

- `import-media.py` → copies from card, tags after copy
- `media-pipeline.py` → processes files already in ready_dir: tag → fix-timestamp → organize → gyroflow
- `organize-by-date.py` outputs `@@dest=` and `@@action=` to stdout; parent parses these
- `perf_baseline.json` lives in `tests/` — delete it to reset after an intentional perf improvement
