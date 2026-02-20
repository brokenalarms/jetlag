# TODO — sliding context window

Read this at the start of each session. Pick ONE task and work on it.
Update this file at the end of the session.

---

## Done recently

- Added Timecop macOS SwiftUI app (`macos/Timecop/`) — profile editor, workflow runner, timezone picker, log output
- Added `generate-gyroflow.py` / `batch-generate-gyroflow.py` for Gyroflow Toolbox FCP plugin
- Integrated gyroflow step into `media-pipeline.py`
- Extracted shared `lib/filesystem.py` utilities (find_media_files, parse_machine_output, cleanup_empty_parent_dirs)
- Performance fixes: batched `tag --add` calls in `tag-media.py` (was looping per tag); batched exiftool writes in `fix-media-timestamp.py` (was 3 separate subprocess calls, now 1)
- Added `tests/test_performance.py` — snapshot harness with regression detection (threshold 5%)
- Removed `name` field from `MediaProfile` — profile name is the YAML dict key, read/written as such; no injection loop needed
- Fixed `updateEnabledSteps()` in `WorkflowView` — was always resetting to all available steps; now correctly intersects with current enabled set
- Added `--tasks [tag fix-timestamp organize gyroflow]` to `media-pipeline.py` — defaults to all; `WorkflowView` passes enabled steps

---

## Open tasks (pick ONE)

### Timecop app

1. **`preserveSource` flag not passed to script** — `WorkflowView.runWorkflow()` binds a toggle to `state.preserveSource` but never adds a `--copy` / `--move` flag to the `import-media.sh` args. `import-media.py` doesn't currently expose this as a CLI flag — need to add it to the script first, then wire up in `WorkflowView`.

2. **`ScriptRunner` stream race condition** — `terminationHandler` calls `continuation.finish()` immediately when the process exits, but `readabilityHandler` callbacks may not have flushed all buffered data yet. Final lines of script output can be lost. Fix: drain both pipes explicitly before finishing the continuation (read until EOF on both file handles before calling `continuation.finish()`).

3. **Scripts not bundled for release builds** — release Xcode build has no copy phase for `scripts/` into the app bundle. `DevConfig.scriptsDirectory` returns `nil` in release, and `Bundle.main.resourcePath + "/scripts"` will not exist.

4. **MapKit / CoreLocation linked but unused** — `project.yml` links `MapKit.framework` and `CoreLocation.framework` but `TimezonePickerView` only uses `TimeZone.knownTimeZoneIdentifiers`. Remove the unused framework dependencies unless a map-based picker is planned.

### Scripts

8. **Performance baseline not yet recorded** — `tests/perf_baseline.json` does not exist yet. Run `pytest tests/test_performance.py -v -s` on the target macOS machine to generate it, then commit the file.

9. **`tag-media.py` still makes a separate exiftool read for Make/Model** — `get_existing_exif_camera()` runs its own exiftool subprocess independent of any other data read for the file. For files where both EXIF and Finder tags need checking, this means 2 reads (tag list + exif) before deciding on writes. Low priority since these are already small reads, but could be merged if tag-media is ever extended to read more EXIF fields.

---

## Architecture reminders

- `import-media.py` → copies from card, tags after copy
- `media-pipeline.py` → processes files already in ready_dir: tag → fix-timestamp → organize → gyroflow
- `organize-by-date.py` outputs `@@dest=` and `@@action=` to stdout; parent parses these
- `perf_baseline.json` lives in `tests/` — delete it to reset after an intentional perf improvement
