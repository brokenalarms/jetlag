# Scripts

## Goal

These scripts manage the workflow for importing videos from different cameras so that they all appear interleaved with each other in a video editor at the time at which they were initially filmed. The time doesn't have to look the same as if the user shot it — the goal is for files to maintain time relative to each other.

Timezone is the timezone a group of videos is shot in, but is a concern unrelated to the profiles in media-profiles.yaml — profiles are camera configurations and could be shot in any number of timezones.

## Design constraints

These are rules that prevent common agent mistakes — they explain why things are structured this way.

- **Why base scripts don't know about profiles**: composability — orchestrators translate profiles to explicit args for base scripts. Base scripts operate on a single file with explicit args. This keeps them reusable outside of profiles.
- **Why batch processing is one file at a time**: resumability on interrupt — complete all pipeline steps on one file before moving to the next, in alphabetical order. If interrupted, resume from the next unprocessed file without repeating steps.
- **Why stdout uses `@@` prefix**: decouples machine data from human-readable output. Child scripts write `@@key=value` to stdout for parents to parse, human messages to stderr. Parents never redirect child stderr (`2>&1` is never used). Never parse human-readable output — that couples presentation to data flow.
- **Why scripts never swallow child output**: compositional output — parents make use of child output rather than suppressing it and adding their own logs. Don't add `--verbose` mode unless instructed.
- **Why YAML uses inline arrays**: agents tend to rewrite `[.mp4, .mov]` as multi-line bullet lists. Use inline format for short lists like file_extensions, companion_extensions, and tags.
- **Why Python uses functional composition**: declarative readability — build up a picture of what needs to be read, what needs to be set, what needs to be done, then do it in the last step. Python was chosen over bash for this reason.
- **Why no hardcoded defaults**: portability across machines. All configuration must come from configuration files (media-profiles.yaml) or environment variables (.env.local). If required config is missing, fail immediately with a clear error directing the user where to add it.
- **Why data is separated from presentation**: formatted text shouldn't be function args. Use structured dicts with descriptive key names as building blocks, then build formatted text at display time.
- **Why batch files pass through all args transparently**: they're thin loops, not filtering layers.

## External tool behavior

These behaviors are not in our code — they're observed from external tools and must be understood to work on timestamp logic.

### Final Cut Pro

- FCP uses file birth date to populate "Content Created" on the import screen, but `Keys:CreationDate` for "Content Created" once imported. Falls back to file birth time if `Keys:CreationDate` is not set.
- Birth time is therefore essential. `setfile -d` sets it. Modification time is NOT set — it naturally reflects when the file was last modified (e.g., by exiftool metadata writes).
- `Keys:CreationDate` can be written with `Z` for UTC or with timezone. iPhone files are saved with TZ. FCP converts the field's timezone to UTC, then displays in current system timezone. So `08:07:22+08:00` becomes `00:07:22 UTC`, then displays as `09:07:22` in Japan (+09:00).
- iPhone footage records `Keys:CreationDate` with timezone, so it should match `DateTimeOriginal`.

### ExifTool

- From ExifTool docs: "According to the specification, integer-format QuickTime date/time tags should be stored as UTC. Unfortunately, digital cameras often store local time values instead (presumably because they don't know the time zone). For this reason, by default ExifTool does not assume a time zone for these values. However, if the API QuickTimeUTC option is set, then ExifTool will assume these values are properly stored as UTC, and will convert them to local time when extracting."
- Our devices DO write UTC time to MediaCreateDate and QuickTime fields — interpret them as real UTC. Verify by adding the timezone from `DateTimeOriginal` and checking it matches. Avoid using the ExifTool `QuickTimeUTC` flag — it's more complicated than handling UTC explicitly.
- There is no such thing as writing to a UTC field as wall-clock time and having video editors recognize it's not UTC anymore. They will take an integer QT UTC field as UTC, or a string field with `Z` as UTC or with timezone.
- For performance: one read call then one write call per file per script. Cache values from the read, accumulate all writes, send in a single exiftool invocation.
- ExifTool fails silently if an `exiftool_tmp` directory exists alongside the target file (leftover from a crashed run). media-pipeline checks for these at startup.

## Timestamp source of truth hierarchy

Priority order — each level has specific rules:

1. **Filename** — `YYYYMMDD_HHMMSS` pattern is the highest-priority source. Never modify filenames.
2. **DateTimeOriginal** — contains local time + timezone offset. Source of truth for shoot time. Never modify unless `--overwrite-datetimeoriginal` is explicitly passed (which also requires `--timezone`).
3. **QuickTime UTC fields** — `MediaCreateDate` etc. Stored as real UTC on our devices. Verify by cross-checking against `DateTimeOriginal` + timezone offset.
4. **File birth time** — FCP fallback. Set by scripts via `setfile -d`.

## Camera quirks

Diagnostic knowledge for understanding unexpected timestamp offsets:

- **GoPro / FAT filesystem**: FAT stores modification time in the camera's local timezone with no TZ info. If the camera is set to +02:00 but the Mac is +09:00, birth/modify times will be ~7 hours off. `MediaCreateDate` is UTC and correct. A non-standard offset in birth vs EXIF time indicates camera TZ mismatch, not a bug.
- **macOS SD card copy**: birth time is often preserved from the source FAT filesystem rather than reset to copy time. This propagates the camera's wrong-TZ birth time to the Mac. The timestamp fix scripts correct this.

## Workflow design

Why import-media and media-pipeline are separate scripts with different modes:

- **import-media** copies from SD card to import_dir (`--copy` mode), tags after copy. Tagging happens after copy because tagging the destination is much faster than tagging on a slow memory card — this is why import-media needs the dest path from organize-by-date.
- **media-pipeline** processes files already in import_dir, organizes into ready_dir (move mode). Flow per file: tag → fix-timestamp → organize → gyroflow (if enabled).
- Both use organize-by-date which outputs `@@dest=` and `@@action=` to stdout for the parent to parse.

## Scenario test specs

Expected behaviors that regression tests must verify:

### fix-media-timestamp
- If `--overwrite-datetimeoriginal` is specified, `--timezone` must be provided
- Files with `YYYYMMDD_HHMMSS` in the filename are first source of truth — filename should never be modified
- `DateTimeOriginal` is next source of truth — should never be modified unless `--overwrite-datetimeoriginal` is specified
- If a file was shot in timezone +0800, with the script run in +0900, then `Keys:CreationDate` should end up with the +0800 timezone, and the birthdate should end up as one hour later
- If a different `--timezone` is specified that doesn't match `DateTimeOriginal`, exit with a warning unless `--overwrite-datetimeoriginal` is specified
- If `DateTimeOriginal` is missing and we change timezones, the QuickTime UTC fields `MediaCreateDate`, file birth date, and `Keys:CreationDate` should all be updated
- If `--preserve-wallclock-time` is specified, the file birthtime should be set back one hour to make the edited file appear in this timezone as if it was shot at the same time

### organize-by-date
- File is sorted into the label template provided
- Directories left empty as a result of a file being moved are deleted immediately
- Directories that were already empty and didn't become so from file moves are left alone
- `.DS_Store` files should be deleted if they're the only thing preventing directory cleanup
- The shell script entry point to each .py file sources `lib/ensure-venv.sh` to set up `PYTHONPATH`

## Source of truth hierarchy

- Base scripts are the source of truth for functionality — push logic down to the lowest level script possible
- Wrapper scripts should be thin orchestration layers, not duplicate functionality
- Path handling, validation, and core logic belongs in the base scripts
- Parent scripts primarily handle: argument parsing for their use case, finding/preparing source data, calling base scripts with appropriate arguments
- Avoid duplicating logic between scripts — if multiple scripts need the same functionality, it belongs in the base script or a shared library
