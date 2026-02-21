# TODO — sliding context window

Read this at the start of each session. Pick ONE task and work on it.
Update this file at the end of the session. Completed work is recorded in commit messages — do not add a "Done" section here.

---

## Open tasks (pick ONE)

### Jetlag app

1. **`preserveSource` flag not passed to script** — `WorkflowView.runWorkflow()` binds a toggle to `state.preserveSource` but never adds a `--copy` / `--move` flag to the `import-media.sh` args. `import-media.py` doesn't currently expose this as a CLI flag — need to add it to the script first, then wire up in `WorkflowView`.

2. **`ScriptRunner` stream race condition** — `terminationHandler` calls `continuation.finish()` immediately when the process exits, but `readabilityHandler` callbacks may not have flushed all buffered data yet. Final lines of script output can be lost. Fix: drain both pipes explicitly before finishing the continuation (read until EOF on both file handles before calling `continuation.finish()`).

3. ~~**Scripts not bundled for release builds**~~ — `project.yml` `postBuildScripts` copies `scripts/` for all configurations; `AppState` uses `Bundle.main.resourcePath` unconditionally. Not a live issue.

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
