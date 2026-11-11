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

## Code layout

`README.md` is the user's guide; keep it in step when a command or flag changes.

```
<command>.sh          what users and the app run; each sources lib/launch.sh
media-profiles.yaml   user config
cli/                  one module per command: argument parsing, validation messages, output
lib/                  the logic, which the pipeline and the tests import directly
  data/               what the code reads rather than imports (filename patterns,
                      timezone tables, exiftool config), found through lib.DATA_DIR
tests/                mirrors lib/ (see tests/README.md)
tools/                vendored binaries
```

A command's name is the same everywhere, in snake_case past the wrapper:
`fix-media-timestamp.sh` → `cli/fix_media_timestamp.py` → `lib/fix_media_timestamp/`.
`lib/launch.sh` resolves the interpreter (`lib/ensure-venv.sh`) and runs
`cli/<command>.py` with `scripts/` on `PYTHONPATH`, so the cli modules import `cli.*`
and `lib.*` from any working directory. A new command is a `cli/` module, a
one-line `<command>.sh` like the others, and its logic in `lib/<command>`;
`tests/test_command_wrappers.py` checks the pairing.

| Command | Logic in `lib/` |
|---|---|
| `media-pipeline` | `media_pipeline/` — runs every step in-process (see below) |
| `fix-media-timestamp` | `fix_media_timestamp/` — `read.read_current` → pure `plan.plan_correction` → `describe.describe_correction` (stderr) → `apply.apply_correction` (one write); `clock_fields` is the table of fields a correction owns |
| `tag-media` | `tag_media.py` |
| `organize-by-date` | `organize_by_date.py` |
| `ingest-media` | `ingest_media.py` |
| `generate-gyroflow` | `generate_gyroflow.py` |
| `archive-source` | `archive_source.py` |
| `verify-card` | `verify_card.py`; its JSONL events are declared in `verify-card-schema.yaml` |
| `probe-camera`, `scan-source`, `report-file-dates` | small enough to stay in the `cli/` module |

Shared modules: `timestamps/` (`sources.py` reads and ranks a file's timestamps:
`read_file()` returns the one `FileReading` every consumer takes a file's winning
time, zone, camera zone, filename time and date folder from —
`tests/timestamps/test_one_derivation.py` fails on a copy anywhere else,
`file_times.py` the file system's birth and modification times, `provenance.py` the
recovery record written with a correction), `exiftool.py` (the one metadata
client), `countries.py` (country → timezone), `command_line.py` (timezone flags and
their resolution, interrupt handling), `profiles.py`, `filesystem.py`, `footage.py`, `data_portion.py` (the data portion
verify-card compares, per format: QuickTime footage, HEIF/AVIF image items, JPEG from
start-of-scan, TIFF raw strips, RAF raw block), `volumes.py` (whether a folder is
on a local disk or across a network, from the mount table).
`cli/results.py` prints a single-file command's result as `@@key=value` lines.

A `cli/` module holds argument parsing, validation messages and output; anything
another command or the pipeline could call belongs in its `lib/` module.

`lib/media_pipeline/` is split by what each part decides:

| Module | Holds |
|---|---|
| `options.py` | `RunOptions`, the frozen command line resolved against the profile, and its validation |
| `preflight.py` | stale exiftool_tmp, then `CHECKS`: each batch check declared once (token, finder, assent flag, which runs it refuses) and run by `run_checks`, one `batch_check` event per finding |
| `consent.py` | `require_consent`, the one terminal-only y/n prompt |
| `stages.py` | one file's trip: a `Stage` per step (`name`, `enabled(opts)`, `run(ctx) -> StageOutcome`) run by `process_file`, which owns `stage_complete` and the single failure exit |
| `batch.py` | `run()`: options → pre-flight → every file → organize conflicts → archive → summary |
| `working_dir.py` | `WorkingDir`, the staging directory and the copies a cancel clears |
| `events.py` | `emit_event`, the JSONL on stdout |

Adding a pipeline step means one `Stage` subclass in `STAGES` plus its entries in
`lib/media_pipeline/pipeline-schema.yaml`: the `stage_complete` token and a `cli.steps` entry. The
`cli` section also lists every flag the app passes; `build_parser()`'s `--tasks`
choices and options are tested against it. `cli/media_pipeline.py` keeps
`build_parser()` and builds the `WorkingDir` its cancel handler closes over.

## External tool behavior

These behaviors are not in our code — they're observed from external tools and must be understood to work on timestamp logic.

### Final Cut Pro

- FCP uses file birth date to populate "Content Created" on the import screen, but `Keys:CreationDate` for "Content Created" once imported. Falls back to file birth time if `Keys:CreationDate` is not set.
- Birth time is therefore essential. It is written as `FileCreateDate` in the same exiftool call as the metadata (exiftool runs `setfile` itself on macOS, after rewriting the file — any metadata write otherwise resets birth time to now). Modification time is NOT set — it naturally reflects when the file was last modified (e.g., by exiftool metadata writes).
- `Keys:CreationDate` can be written with `Z` for UTC or with timezone. iPhone files are saved with TZ. FCP converts the field's timezone to UTC, then displays in current system timezone. So `08:07:22+08:00` becomes `00:07:22 UTC`, then displays as `09:07:22` in Japan (+09:00).
- iPhone footage records `Keys:CreationDate` with timezone, so it should match `DateTimeOriginal`.

### ExifTool

- There is no such thing as writing to a UTC field as wall-clock time and having video editors recognize it's not UTC anymore. They will take an integer QT UTC field as UTC, or a string field with `Z` as UTC or with timezone.
- For performance: one read call then one write call per file per script. Cache values from the read, accumulate all writes, send in a single exiftool invocation.
- ExifTool fails silently if an `exiftool_tmp` directory exists alongside the target file (leftover from a crashed run). media-pipeline checks for these at startup.
- macOS never lets a birth time stand later than the modification time: setting the modification time pulls the birth time back to it. `-P` puts the card's modification time back after a write, and that can be earlier than the corrected birth time (footage shot west of the Mac's zone), which would clamp it. So a write carrying `FileCreateDate` does not use `-P`: the modification time is left as the time of the write, which is always after the shooting time, and nothing is clamped. Jetlag never sets the modification time itself. `SetFile`, run separately, never hit this. Linux CI tracks no birth time, so only the macOS suite catches it.
- ExifTool cannot write Insta360 X6 `.insv` files (firmware v1.1.7). Without `-m` it refuses with the minor error `Terminator found in Meta`; with `-m`, `Corrupted Insta360 trailer`. So `write_tags` retries a refusal made only of minor errors once with `-m`, and raises `Insta360TrailerCorrupted` for the trailer; the correction then sets the file times alone and reports `metadata_skipped`. File-time-only writes succeed on these clips. X4 files write normally.

## Timestamp source of truth hierarchy

The per-field truth table — what each field means, when a QuickTime date counts as
UTC, the full ranking, and the `--timezone`/`--force-timezone`/`--time-offset` rules —
lives in `/docs/timestamp-fields.md`. Required reading before touching timestamp code.
Summary only:

- Zoned tags rank first, then UTC sources (a `Z` tag, a filename-corroborated clock),
  then the filename, then an uncorroborated clock, then bare tags — see the ranking
  table in `docs/timestamp-fields.md`.
- The filename is the first truth for local wall-clock time in the absence of
  disconfirming metadata; `--update-filename-dates` renames files to match corrections.
- QuickTime dates are trusted as UTC per file, on evidence, never globally — and never
  via exiftool's `QuickTimeUTC` option.
- Only `--time-offset` moves the actual time; everything else relabels.

## Camera quirks

Diagnostic knowledge for understanding unexpected timestamp offsets:

- **GoPro / FAT filesystem**: FAT stores modification time in the camera's local timezone with no TZ info. If the camera is set to +02:00 but the Mac is +09:00, birth/modify times will be ~7 hours off. `QuickTime:CreateDate` is UTC and correct. A non-standard offset in birth vs EXIF time indicates camera TZ mismatch, not a bug.
- **macOS SD card copy**: birth time is often preserved from the source FAT filesystem rather than reset to copy time. This propagates the camera's wrong-TZ birth time to the Mac. The timestamp fix scripts correct this.

## Workflow design

`media-pipeline` is the single entry point for all media processing. The pipeline has a fixed frame — **ingest** and **output** always run — with optional processing steps in between:

```
INGEST (always) → [tag] → FIX-TIMESTAMP (always) → OUTPUT (always) → [gyroflow] → [archive-source]
```

- **Ingest** copies files from the source (SD card or local directory) to a temporary working directory — `<target>/.jetlag-working` unless `--working-dir` overrides it, so staging shares a volume with the destination and **Output**'s move is a rename rather than a second copy. Source files are read-only inputs — never modified.
- A protected source file (user-immutable flag — a camera's "Protect") is staged as an unlocked copy, since every later stage rewrites or moves that copy. An apply asks first: the batch reports `protected_sources` and stops unless `--unlock-protected` is given (or answered at a terminal prompt). The source keeps its lock.
- **Tag** (optional) and **fix-timestamp** (always: the app's Set Timestamps, so every run needs `--timezone`) operate on the working copy.
- **Output** moves processed files from the working directory to `ready_dir` via organize-by-date (date-based folder structure).
- **Gyroflow** generates stabilization projects on the file now in `ready_dir`.
- **Archive-source** acts on the source folder after all files are processed (archive/rename, or delete processed files). Delete removes only files verify-card matches on every `--backup-location` (or that `archive-source --accept` names); with no location it deletes nothing.

## Scenario test specs

Expected behaviors that regression tests must verify:

### fix-media-timestamp
- If `--infer-from-filename` is specified, `--timezone` must be provided
- Source ranking follows the "Timestamp source of truth hierarchy" section above and `docs/timestamp-fields.md` — not restated here
- If a file was shot in timezone +0800, with the script run in +0900, then `Keys:CreationDate` should end up with the +0800 timezone, and the birthdate should end up as one hour later
- If a different `--timezone` is specified that doesn't match `DateTimeOriginal`, this is informational (shown in diff) — not blocking
- If `DateTimeOriginal` is missing and we change timezones, the QuickTime UTC fields `CreateDate`, file birth date, and `Keys:CreationDate` should all be updated
- If `--preserve-wallclock-time` is specified, the file birthtime should be set back one hour to make the edited file appear in this timezone as if it was shot at the same time

### organize-by-date
- File is sorted into the label template provided
- Directories left empty as a result of a file being moved are deleted immediately
- Directories that were already empty and didn't become so from file moves are left alone
- `.DS_Store` files should be deleted if they're the only thing preventing directory cleanup

## Python runtime

- Scripts must run on the Python macOS ships (3.9) so users install nothing — see `docs/specs/python-runtime.md`
- Wrappers exec `$JETLAG_PYTHON` through `lib/launch.sh`, resolved by `lib/ensure-venv.sh`, never a bare `python3`
- A module using `X | None` annotations needs `from __future__ import annotations`; `tests/test_python_compatibility.py` enforces this

## Source of truth hierarchy

- Base scripts are the source of truth for functionality — push logic down to the lowest level script possible
- Wrapper scripts should be thin orchestration layers, not duplicate functionality
- Path handling, validation, and core logic belongs in the base scripts
- Parent scripts primarily handle: argument parsing for their use case, finding/preparing source data, calling base scripts with appropriate arguments
- Avoid duplicating logic between scripts — if multiple scripts need the same functionality, it belongs in the base script or a shared library
