# TODO — sliding context window

Read this at the start of each session. Pick ONE task and work on it.
Update this file at the end of the session. Completed work is recorded in commit messages — do not add a "Done" section here.

---

## Open tasks (pick ONE)

### Jetlag app

1. **`preserveSource` flag not passed to script** — `WorkflowView.runWorkflow()` binds a toggle to `state.preserveSource` but never adds a `--copy` / `--move` flag to the `import-media.sh` args. `import-media.py` doesn't currently expose this as a CLI flag — need to add it to the script first, then wire up in `WorkflowView`.

2. **`ScriptRunner` stream race condition** — `terminationHandler` calls `continuation.finish()` immediately when the process exits, but `readabilityHandler` callbacks may not have flushed all buffered data yet. Final lines of script output can be lost. Fix: drain both pipes explicitly before finishing the continuation (read until EOF on both file handles before calling `continuation.finish()`).

3. **MapKit / CoreLocation linked but unused** — `project.yml` links `MapKit.framework` and `CoreLocation.framework` but `TimezonePickerView` only uses `TimeZone.knownTimeZoneIdentifiers`. Remove the unused framework dependencies unless a map-based picker is planned.

4. **Timezone suffix for group folder** — `--subfolder` / `folder_template` groundwork is done. Remaining:
   - Rename `--subfolder` → `--group` in `media-pipeline.py` and app (group is the right semantic — it groups files by shooting location/timezone)
   - Add `--group-timezone` flag to `media-pipeline.py` (on by default): when set, appends the timezone offset to the group folder name, e.g. `Japan (+0900)`. App should expose a toggle so users can opt out.
   - App: rename the "Subfolder" field label to "Group"; add help text noting that date-range names (e.g. `05-06 Korea`) don't work well when backing up mid-trip since the end date isn't known yet
   - Tests: `--group Japan --timezone +0900` with `--group-timezone` → folder named `Japan (+0900)`; with `--no-group-timezone` → folder named `Japan`

### Scripts

5. **Performance baseline not yet recorded** — `tests/perf_baseline.json` does not exist yet. Run `pytest tests/test_performance.py -v -s` on the target macOS machine to generate it, then commit the file.

6. **`tag-media.py` still makes a separate exiftool read for Make/Model** — `get_existing_exif_camera()` runs its own exiftool subprocess independent of any other data read for the file. For files where both EXIF and Finder tags need checking, this means 2 reads (tag list + exif) before deciding on writes. Low priority since these are already small reads, but could be merged if tag-media is ever extended to read more EXIF fields.

### Web
