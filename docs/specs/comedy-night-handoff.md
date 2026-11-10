# Handoff: Comedy night follow-ups, for a local macOS session

Read `timestamp-handoff.md` (the principles), `comedy-night-timestamps.md` (the items)
and `preflight-checks.md` (the batch-check design) first. This file holds the state of
the branch and what is left.

## Branch

`claude/comedy-night-timestamps-4mczz6`, draft PR #285. It was built in a Linux cloud
session: the scripts suite and lint pass there, but **nothing under `macos/` has been
compiled or run**, and the birth-time tests were skipped. First:

```
git fetch origin && git checkout claude/comedy-night-timestamps-4mczz6
make test-scripts      # birth-time tests run only on macOS
make test-macos        # never run on this branch
```

Fix whatever fails before anything else; Swift compile errors are possible.

## What the branch holds

1. **Item 1 is done.** `read_file()` in `scripts/lib/timestamps/sources.py` returns one
   `FileReading` per file, built from the cached read. It provides `best()`,
   `tagged_zone`, `camera_zone`, `zone`, `declared_offset()`, `local_time()` and
   `date_folder()`. The parallel copies are deleted. The date folder is the file's date
   in the declared `--timezone`, never the modification time. The mixed-zone guard
   compares `FileReading.zone` (a tag's zone, else the camera zone from the UTC clock
   against the filename). `tests/timestamps/test_one_derivation.py` fails on any new
   copy.
2. **Item 4 is decided and done: Set Timestamps is always on.** `fix-timestamp` is in
   the schema's fixed frame (no task token). `--tasks` no longer names it and accepts
   zero names. `--timezone`/`--location` is required. `ProvenanceStage` is deleted. In
   the app: `PipelineStep.isAlwaysOn` is derived from `taskToken == nil`, the label is
   "Set Timestamps" ("Set TS"), and `--tasks` and `--timezone` are always passed. The
   Swift tests in `PipelineArgsTests` and `FixTimestampPreviewTests` were edited blind.
   Check them first.
3. **Specs:** `preflight-checks.md` is new. `comedy-night-timestamps.md` items 3 and 4
   record the user's decisions.

## Reviewer checks in the app

- [ ] The Set Timestamps card shows as required and cannot be toggled off.
- [ ] A run can't start without a timezone.
- [ ] Two clips whose names imply different camera zones (correct UTC clock on both)
      stop with the mixed-timezones dialog listing both zones.
- [ ] A clip with no DateTimeOriginal and no date in its name lands in the folder for
      its date in the declared zone.

## Left to do, in order

1. **Merge #285** once `make test-scripts` and `make test-macos` pass.
2. **The batch-check sequence** (`preflight-checks.md`): one new PR from main covering
   the script, the schema and Swift together. The Swift side is about 190 references
   across 18 files: `PipelineEvent`, `RunTranscript`, `AppState`, `WorkflowSession`
   (the per-check state triples and `clearRunAssent`), `WorkflowView` (four alerts),
   `PipelineSummary`, `Strings`, `DiffTableView`, and the tests `CameraCheckTests`,
   `OrganizeConflictTests`, `AppStateTests`, `DryRunFreshnessTests`,
   `RunTranscriptTests`, `CameraMismatchTests`, `ScriptedRunTests` and
   `PipelineSchemaContractTests`. Mixed zones gain a `none` group for files with no zone
   evidence: the user expects zoned plus unzoned to count as mixed.
3. **Item 3:** a write exiftool refuses as `Corrupted Insta360 trailer` is skipped with a
   warning rather than failing the file. Birth time, filename and date folder are still
   corrected, and the row gets its own outcome token in `pipeline-schema.yaml` and the
   app. Open question for the user: whether this is reported through the same
   batch-check shape (it happens per file, during the run).
4. **Item 2:** run `exiftool -a -G1 -s -time:all` on clip 001 on the T9. On main, an
   X6-shaped clip already ranks its clock as corroborated UTC (filename − clock =
   −07:00) and corrects to `15:28:02+08:00`. The 10 Oct code read
   `QuickTime:MediaCreateDate`, while main reads the movie header. The dump shows
   whether any ranking change is still needed. Either way, add the pinning test the
   spec describes: X6 shape, `--timezone +08:00`, rename under
   `--update-filename-dates`, UTC fields never rewritten.
5. **Item 5:** `tag-media.sh` run on its own resets birth time. Its write must carry
   `FileCreateDate` (no `-P`). Add a macOS test.
6. **Item 6:** re-run the seven clips on the T9 once items 1–3 land. Tell the user
   before the rename because of the NAS backup (finish 004 first, or use rsync
   `--fuzzy` with a delayed `--delete`).

## Found along the way

- With every optional step off, the app used to omit `--tasks`, so the pipeline ran its
  defaults (tag, gyroflow). Fixed on the branch: `--tasks` is always passed.
- `organize-by-date.sh` now takes `--timezone`. Without it, a UTC-only clip is filed
  under its UTC date.
