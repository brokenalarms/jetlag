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
- Added `tests/test_performance.py` — snapshot harness with regression detection

---

## Open tasks (pick ONE)

### Timecop app

1. **`ProfileService.write` corrupts YAML** — Yams encodes `name` as a field inside each profile dict value, but the YAML format uses the profile name as the dict key. On save, a `name:` key gets added inside each profile block that the scripts don't expect. Fix: implement a custom `Encodable` on `MediaProfile` that omits `name`, or strip it from the encoded output before writing.

2. **`updateEnabledSteps()` logic is wrong** — `WorkflowView.swift:288`: `state.enabledSteps.intersection(available).union(available)` always equals `available` (intersecting then re-unioning negates the intersection). The intent is to drop steps that aren't available for the new profile while preserving which available steps the user had toggled. Fix: `state.enabledSteps = state.enabledSteps.intersection(Set(state.availableSteps))`

3. **`preserveSource` flag not passed to script** — `WorkflowView.runWorkflow()` binds a toggle to `state.preserveSource` but never adds a `--copy` / `--move` flag to the `import-media.sh` args. Need to confirm what flag the script accepts and wire it up.

4. **`ScriptRunner` stream race condition** — `terminationHandler` calls `continuation.finish()` immediately when the process exits, but `readabilityHandler` callbacks may not have flushed all buffered data yet. Final lines of script output can be lost. Fix: drain both pipes explicitly before finishing the continuation (read until EOF on both file handles before calling `continuation.finish()`).

5. **Disabled pipeline steps not reflected in script args** — individual step toggles (tag, gyroflow) have no corresponding `--skip-*` args passed to `media-pipeline.sh`. Fix: check which steps are enabled vs available and pass appropriate skip flags.

6. **Scripts not bundled for release builds** — release Xcode build has no copy phase for `scripts/` into the app bundle. `DevConfig.scriptsDirectory` returns `nil` in release, and `Bundle.main.resourcePath + "/scripts"` will not exist.

7. **MapKit / CoreLocation linked but unused** — `project.yml` links `MapKit.framework` and `CoreLocation.framework` but `TimezonePickerView` only uses `TimeZone.knownTimeZoneIdentifiers`. Remove the unused framework dependencies unless a map-based picker is planned.

### Scripts

8. **Performance baseline not yet recorded** — `tests/perf_baseline.json` does not exist yet. Run `pytest tests/test_performance.py -v -s` on the target macOS machine to generate it, then commit the file.

9. **`tag-media.py` still makes a separate exiftool read for Make/Model** — `get_existing_exif_camera()` runs its own exiftool subprocess independent of any other data read for the file. For files where both EXIF and Finder tags need checking, this means 2 reads (tag list + exif) before deciding on writes. Low priority since these are already small reads, but could be merged if tag-media is ever extended to read more EXIF fields.

---

## Architecture reminders

- `import-media.py` → copies from card, tags after copy
- `media-pipeline.py` → processes files already in ready_dir: tag → fix-timestamp → organize → gyroflow
- `organize-by-date.py` outputs `@@dest=` and `@@action=` to stdout; parent parses these
- `perf_baseline.json` lives in `tests/` — delete it to reset after an intentional perf improvement
