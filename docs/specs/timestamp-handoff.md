# Handoff: timestamp source of truth

Read `timestamp-source-of-truth.md` first — it holds the rules and the reasoning. This
file is what a fresh agent needs to pick up the work, and the state of the user's data.

## What landed

PR #137, squashed to `9911786`. One behaviour change to timestamps:
`get_best_timestamp()` now prefers a QuickTime date over a camera filename that
contradicts it, where the file itself shows that date to be an instant. Everything else
in that PR is unrelated (Python 3.9 runtime, per-file DST resolution, two workflow UI
defects, a gyroflow CI fix).

Verified against the reported file, `LRV_20260104_033532_01_001.lrv`: corrects to
`2026-01-04 07:35:32+13:00`, and no longer proposes a QuickTime rewrite.

## The user's own words on the model

Worth keeping, because several plausible-sounding designs contradict them:

- "jetlag is not about actually changing times in bulk at all, just correcting how they
  appear in this very typical case where we change countries but forget to update the
  zone."
- "UTC is going to be correct no matter what the timezone, it's just whether I set TZ to
  8 or 9." A camera clock keeps absolute time; the zone is a label on it.
- "the only thing that should move the actual time IIRC is if we provide --offset."
- `--force-timezone` is a confirmation gate — "the point of the cli to not proceed if the
  file already has a TZ, the user must run again with this added to explicitly confirm
  they want to overwrite." It should not carry arithmetic.
- The filename is "first source of truth for wallclock local time, in the absence of
  disconfirming metadata (UTC)."
- On the hierarchy: "it's entirely dependent on the device, every device is different as
  to what metadata they write or don't. this is why we have the hierarchy." Do not
  replace it with a rule derived from two cameras.
- On process: minimal change first, pinned by tests, and only then refactors — and those
  refactors "only to better make sure that there are only SOT for certain actions and no
  duplicate code."

## Everything under "Not done" has landed

Items 1–7 of the earlier list are on `main` (PRs #140–#165, #163 in particular: one clock-field
table drives both the comparison and the write, so a stale movie header can no longer survive
a run that found the track atoms correct). The test debt is paid: `TestIdempotenceAcrossRanking`
(reprocess == pristine per ranking source), `original_epoch == corrected_epoch` per source,
header/track agreement, and offset-bearing `DateTimeOriginal` conversion are all covered.
`docs/timestamp-fields.md` is the per-field truth table and its ranking matches
`get_best_timestamp()`; the vocabulary is "corroborated UTC" (a UTC-specified clock the
filename corroborates), never "instant"/"proven".

## The Korea run — where it is

The first real-library run of the corrected pipeline, 2026-08-26. Everything below was checked
independently with `exiftool`, never with jetlag itself.

- **Source:** `/Volumes/Samsung_990/Videos/Source Video/Insta360/Import/2025/08-09 - South Korea`,
  448 `.insv`, camera on `+09:00` throughout. Untouched by the run (copy semantics; the archive
  step never ran). The volume now mounts as `Samsung_990` (underscore); the profile yaml may
  still say `Samsung 990`.
- **Before snapshot:** `.ralph/korea-check/before.csv` (all clock fields, XMP DTO, LogComment,
  mtime). Two populations: first half 08-15→08-24 (137 files) already carried
  `XMP-exif:DateTimeOriginal = filename+09:00` from an earlier jetlag run, tracks correct, movie
  header 8 h stale (the old `+01:00` carry-over write); second half 08-30→09-27 (311 files)
  naive, header = tracks = filename − 9 h.
- **Apply (grouped destination `Ready/2025/08-09 - South Korea/<date>/`):** 379 of 448
  completed before the pipeline wedged (see "The wedge"). `.ralph/korea-check/after-group.csv`.
  All 379 pass every check: first-half DTO byte-identical (idempotent), header healed to equal
  the tracks; second-half DTO written as the camera's instant `+09:00`; every file has
  `Keys:CreationDate` = DTO, `CreateDate` = `MediaCreateDate` = `TrackCreateDate` = the
  original UTC (tracks untouched, no epoch moved), and a `LogComment` provenance record.
- **Not yet processed (69):** 2 of 09-17, then 09-18 (16), 09-19 (8), 09-20 (20), 09-21 (10),
  09-22 (9), 09-27 (4). The user cancelled and the wedged tree was killed. Re-run the whole
  folder with the same settings and take the Overwrite prompt: the correction is idempotent,
  so the 379 are re-verified for free and the 69 complete. Then re-snapshot and re-run the
  check below; expect 448/448.
- **Duplicate output in `Ready/2025/2025-08-15` … `2025-09-17` (22 plain-date folders,
  379 files):** an earlier accidental run with no group folder, wedged at the same point.
  Same 379 filenames, all with provenance and healed headers, byte-identical to the grouped
  copies on the three sampled (`md5`). `.ralph/korea-check/plain-dates.csv`. **Safe to delete
  once the grouped tree is complete — but only on the user's explicit say-so; nothing in
  this handoff authorises deleting anything under `/Volumes`.**

### The check

Snapshot (read-only):

```
exiftool -r -csv -ext insv -api QuickTimeUTC=0 -FileName -Directory \
  -XMP-exif:DateTimeOriginal -Keys:CreationDate -QuickTime:CreateDate \
  -QuickTime:MediaCreateDate -QuickTime:TrackCreateDate -XMP-xmpDM:LogComment \
  -FileModifyDate "<tree>" > after.csv
```

Compare against `before.csv` per filename: DTO ends `+09:00` and its instant equals the
original `MediaCreateDate` (UTC); `Keys:CreationDate` == DTO; `CreateDate` ==
`MediaCreateDate` == `TrackCreateDate` == the original `MediaCreateDate`; `LogComment`
present; first-half DTO unchanged. The Python that does this is in the 2026-08-26 session
transcript and is 30 lines; rewrite it rather than hunting for it.

### The wedge, and what it taught

At file ~380 the pipeline, `jetlag-metadata` and `exiftool` were all asleep at 0 %.
`jetlag-metadata` had attached a stderr pipe to `exiftool -stay_open` and never read it; every
`.insv` write emits an "Insta360 trailer" warning; the 16 KB pipe filled and exiftool blocked
before printing `{ready}`. Fixed in #197 (all three clients drain; tests flood stderr with
200 KB through the real binary). The app bundles `jetlag-metadata` at build time, so a rebuild
is required to pick it up. Lessons that generalise: a child's pipe nobody reads is a deadlock
with a delay; the 3-file perf/streaming guards cannot see anything that needs hundreds of
files; and `Cancel` only terminated the top process — jetlag-acd (in progress) makes it tear
the whole process group down.

## Principles the user restated this session (do not re-derive)

- **The script is the source of truth; the app composes arguments and renders tokens.** No
  label, status or outcome is inferred in Swift from the presence of a field. Tokens are
  enumerated in `scripts/pipeline-schema.yaml` and pinned on both sides by contract tests
  (`test_pipeline_schema.py`, `PipelineSchemaContractTests`). Add a token on one side only
  and a test fails.
- **The ingest directory is never touched.** The output is a new file at the destination;
  `organize_result.action` is relative to the source (`copied`, never `moved`, for a staged
  file). Archiving the source is the archive step's own outcome, not the row's.
- **The working directory is an implementation detail.** No log line names it (#196); it
  appears in output only when preserved for inspection after a failure.
- **Zoned tags outrank the clock.** A camera-written zoned tag always agrees with the clock;
  where they disagree the tag was written by something other than the camera, and repairing
  that is out of scope (never back-heal earlier bugs). "Proven instant" ranking was filed and
  withdrawn (jetlag-peo).
- **Idiomatic AppKit over overrides.** Scroller style follows the user's system setting
  (overlay + `flashScrollers()` on overflow), never a forced `.legacy`. Layout is derived from
  content: the form declares one width, the panel one minimum and one maximum (2× sidebar +
  form), and `windowResizability(.contentSize)` does the rest. No timers, no dispatch-later.
- **Minimal change first, pinned by a test that would have caught it**, then refactor only to
  remove duplicate sources of truth.

## Environment notes

- Builds under `.ralph/` must pass `JETLAG_BUNDLE_SUFFIX=.dev JETLAG_PRODUCT_SUFFIX=" Dev"`
  (a pre-build guard enforces it); the product is `Jetlag Dev.app`,
  `com.daniellawrence.Jetlag.dev`, with its own `~/Library/Application Support/Jetlag Dev/`.
  The user's own build is the unsuffixed one from the main checkout.
- Profiles live in `~/Library/Application Support/<app name>/media-profiles.yaml`, seeded from
  the bundled yaml on first launch (#169); the Settings override points a dev build at the
  repo's `scripts/media-profiles.yaml`.
- `scripts/tests/perf-gate.sh` records the Python perf baseline from `origin/main` and
  compares — the only perf comparison that ever runs locally (the baseline file is gitignored,
  so `test_performance.py` alone just prints). CI's 3-file comparison is noise-prone
  (jetlag-3y8 landed to interleave runs and skip Swift-only PRs).
- `StreamingPerformanceTests` asserts the second half of a streamed run costs no more than
  the first; it is what stands between the app and O(n²) per line/row.
- The scripts test suite leaked `exiftool -stay_open` processes after a full run
  (jetlag-rw4, released). Check `ps` after running it.
- `bd` works; `git push origin <branch>` works; CI runs on `pull_request` only, Ubuntu only —
  the macOS target is gated locally, so a PR's Swift tests are only as good as the local run.
