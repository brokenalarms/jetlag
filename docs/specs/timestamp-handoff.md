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

## Not done, in the order that makes sense

Each is described in `timestamp-source-of-truth.md` under "Not yet done".

1. **`--force-timezone` becomes a gate only.** Delete the block at
   `fix-media-timestamp.py:723-730` that rebuilds the timestamp from the wall clock. It
   currently moves the instant by the difference between the two zones.
2. **Offset-bearing sources honour `--timezone`.** `fix-media-timestamp.py:309` and `:314`
   use the embedded value verbatim and never read the declared zone, so a user who says
   "I was in New Zealand" is ignored on any file carrying a zoned tag.
3. **Clock writes reach the track atoms.** `write_quicktime_createdate()` sends
   `-QuickTime:CreateDate=` and `-QuickTime:MediaCreateDate=`, which only reach the movie
   header. This is why imported files disagree with themselves.
4. **Provenance record.** Write-once XMP namespace holding the original clock fields and
   filename, never overwritten, never read back as a timestamp source. It exists so a
   future defect is recoverable outside the app. This becomes important the moment (3)
   lands, because until then the track atoms are an accidental backup.
5. **The mismatch stops blocking.** `media-pipeline.py:707-723` exits 1 when an embedded
   offset differs from the declared one. `time-correction-pipeline-step.md:99` specifies
   the opposite — informational, with dry-run plus explicit apply as the gate. PR #111
   introduced the block against that spec.
6. **One rule for when `--timezone` is required.** The app demands it whenever the step is
   enabled (`AppState.validateTimezone`); the script only for `--infer-from-filename` and
   `--time-offset`; the CLI help claims it is only needed when `DateTimeOriginal` lacks a
   zone. The spec says always. The user's instruction: mirror one rule, and the UI should
   hold no logic beyond assembling the command.
7. **`scripts/AGENTS.md:46`** still states the filename is the highest-priority source and
   that filenames are never modified. Both are now wrong.

## Test debt

- `test_fix_media_timestamp.py:60` is the only idempotence test. Its fixture already
  carries a zoned `DateTimeOriginal` and it runs with no declared timezone, so it
  exercises the one path that cannot regress. The assertion that would have caught this
  bug is that reprocessing a corrected file yields what processing a pristine copy yields.
- Fixtures cannot express a metadata/filename conflict unless a QuickTime date is written
  explicitly — the ffmpeg-generated template carries `0000:00:00`. See
  `TestQuickTimeInstantVersusFilename` for the pattern.
- `test_generate_gyroflow.py::TestMissingBinary::test_missing_binary_skips_gracefully`
  passes in CI but fails on macOS: the vendored binary is executable there, and is killed
  (`exit code -9`) rather than failing to exec, so stderr does not contain "not found".
  The binary is unsigned. Not investigated.

## The user's library

Nothing here is jetlag's job to repair — the user was explicit that this is separate work.

- **The card** `/Volumes/Untitled/DCIM` holds 108 `.insv` from the New Zealand trip,
  unprocessed. Camera was on Japan time: `filename − MediaCreateDate = +9h` on every file.
- **`Insta360/Import/`** holds 1714 `.insv` originals. Their `DateTimeOriginal` is in the
  `XMP-exif` group — written by an earlier jetlag run, some carrying `+01:00` declared for
  a different trip. Their track-level UTC is intact, so they are recoverable by
  reprocessing with the right zone. Their movie headers are not, and will not repair
  themselves until (3) above lands.
- **`Insta360/Ready/`** holds 117 `.mp4` and zero `.insv` — Insta360 Studio exports that
  went through the pipeline (`Lavf60` encoder, 3840x2160, jetlag-written Make/Model). The
  user expects Ready to hold `.insv` and `Exports/` to hold `.mp4`. The insta360 profile
  lists `.mp4` in `file_extensions`, and the X4 in 360 mode never produces one, so that
  entry can only ever match a Studio export.
- **Korea** (448 files in Import) is the same shape as the NZ card: camera on `+8` while
  in Seoul. Converting gives `14:08:51+09:00`. Whether that is right depends on whether
  the camera was still on Taipei time, which only the user knows — it shows in the
  dry-run diff.
- **Scotland and Netherlands** carry `MediaCreateDate 2018:11:24`, a reset clock. They are
  the reason the filename must keep winning when the QuickTime date is implausible, and
  the reason the original filename-first rule was written.

Writing to `.insv` is safe and lossless: the Insta360 trailer survives byte-identical
(md5 `d2d8bbbf…` before and after, relocated by the size of the inserted XMP). Verified on
a copy; Studio was not opened against the result.

## Environment notes

- `git push` is blocked in this session unless the remote and branch are named explicitly:
  `git push origin <branch>` works, bare `git push` is denied.
- `bd` is unusable — every command fails with `pending schema migrations alter
  pre-existing dirty tables: comments, events, issues`, including `bd migrate`. Issues
  discovered during the session went to `docs/TODO.md` instead.
- CI runs on `pull_request` only, so `main` has never been exercised by it. Green
  checkmarks on `main` are the auto-rebase workflow.
- `scripts/media-profiles.yaml` has uncommitted local edits belonging to the user (volume
  paths moved from `Extreme GRN` to `Samsung 990`). Leave them alone.
