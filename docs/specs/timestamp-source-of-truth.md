# Timestamp source of truth

The ranking change and its guard are implemented. Everything under "Not yet done" is
described here but not built, and is deliberately separate work.

## Problem

Correcting an Insta360 card shot in New Zealand with the camera still set to Japan
produced no correction at all. Every file's corrected time matched the time already in
its filename, and applying the fix overwrote the file's UTC with a value four hours from
the truth.

For `LRV_20260104_033532_01_001.lrv`:

| | value |
|---|---|
| filename | `2026-01-04 03:35:32` |
| `MediaCreateDate` | `2026-01-03 18:35:32` |
| `DateTimeOriginal` | absent |

Both describe one instant, `18:35:32Z`, which in Auckland is `07:35:32+13:00`.
`get_best_timestamp()` returns the filename, because the filename rule outranks
`MediaCreateDate`. The declared timezone is then appended to the filename's digits
rather than used to convert the instant.

The same file copied under a name that does not match the camera pattern corrects to
`07:35:32+13:00`. Identical bytes, four hours apart, decided by whether the filename
matched a regex.

## What each source knows

A camera clock keeps absolute time. Its timezone is a label applied to that clock, so
flying without re-syncing leaves the clock correct and the label stale. That is the
scenario this step exists for.

| Source | Records | Zone |
|---|---|---|
| `CreationDate` ending `Z` | instant | UTC by marker |
| QuickTime `CreateDate`, `MediaCreateDate`, `TrackCreateDate` | instant *or* local time — see below | UTC by specification, but not by every device |
| `DateTimeOriginal` + offset | local time | explicit |
| `CreationDate` + offset | local time | explicit |
| filename | the digits the camera displayed | **none** — no filename pattern carries a zone |
| `DateTimeOriginal`, no offset | local time | **none** |
| file birth/modify time | varies | filesystem-dependent |

Container defaults differ. QuickTime dates are seconds since 1904 UTC, so a missing
offset means UTC. QuickTime carries `DateTimeOriginal` natively in the `IDIT` and
UserData `date` atoms, but a bare `-DateTimeOriginal=` write lands in `XMP-exif`, whose
ISO-8601 values carry an offset. In EXIF proper, on stills, `DateTimeOriginal` has no
offset at all, which is why EXIF 2.31 added `OffsetTimeOriginal`. A bare
`DateTimeOriginal` accompanied by that tag is read as one zoned value, so it ranks as
explicit rather than naive.

Devices vary in what they write and in whether they honour the QuickTime specification —
some write local time into fields defined as UTC. The hierarchy exists because of that
variation and is kept. What a device wrote is established per file, from evidence in the
file, never assumed from the model.

## Corroborating a UTC-specified field

The clock atoms are UTC by specification. The filename — the camera's own wall clock —
either corroborates that or it does not:

| Evidence | Conclusion |
|---|---|
| `filename − clock` is a legal zone offset | corroborated UTC; the difference is the camera's zone setting |
| `filename − clock` is zero | undecidable — uncorroborated |
| `filename − clock` is not a legal offset | the clock is broken; the filename wins |
| no filename digits | uncorroborated — still UTC by specification |

A zoned tag never takes part: a camera-written zoned tag comes from the same clock plus
the zone setting, so the two always agree; where they disagree the zoned tag was written
by something other than the camera. Zoned tags simply rank above the clock.

A legal zone offset runs from **−12:00 to +14:00** in 15-minute steps. That is the range
of a single zone's offset from UTC, which is the quantity being tested here; the 26-hour
figure is the span between two zones, a different measurement.

`is_valid_timestamp()` only rejects `0000:00:00`. Scotland footage carries
`MediaCreateDate 2018:11:24` against a 2025 filename — a battery-reset clock, six years
from any legal offset, and the reason its filename must keep winning.

## Camera states

| Clock | Zone label | QuickTime date | Filename | Correction |
|---|---|---|---|---|
| right | stale | correct instant | wrong for the location | convert the instant into the declared zone |
| right | right | correct instant | correct | convert; both agree, nothing changes |
| wrong | any | garbage | right | filename, plus `--time-offset` for the clock error |

## Rules

### Ranking

First match wins:

1. `DateTimeOriginal` with offset
2. `CreationDate` with offset
3. `CreationDate` ending `Z` — requires a declared timezone
4. clock (`MediaCreateDate`) corroborated as UTC by the filename — requires a declared timezone
5. filename timestamp
6. clock (`MediaCreateDate`) uncorroborated — UTC by specification only
7. `DateTimeOriginal` without offset
8. file birth/modify time

Rows 3 and 4 need a declared timezone because UTC cannot be labelled without one; with
no timezone they are skipped and the highest-ranked label wins instead.

Zoned tags outrank everything: they carry both the digits and their zone, so nothing is
assumed. The corroborated clock outranks the filename because a camera left on the
previous country's time writes a filename that is wrong for where it was shot while the
clock is not. The uncorroborated clock ranks below the filename but above the bare tags:
its specification says what its digits mean, a bare tag's says nothing.

### Instant preservation

Only `--time-offset` may change a file's instant. Every other operation relabels.

When the winning source is an instant, the corrected time is that instant expressed in
the declared zone. The file's clock fields are then rewritten with a value they already
held, so the correction is a no-op there.

When the winning source is naive — rows 5, 7, 8 — there is no instant to preserve.
Its digits are taken as local time in the declared zone, which is correct exactly when
the camera's clock was set to that zone, and the clock fields are rewritten to the
instant that implies.

### Writes

Corrections are written to the standard fields so that any application reads the
corrected time, not only this one. That includes every clock field — the movie header
and the track atoms together.

A QuickTime correction sends `-QuickTime:CreateDate=`, `-QuickTime:MediaCreateDate=` and
`-QuickTime:TrackCreateDate=` in one call, reaching the `mvhd` header, the per-track
`mdhd` atoms and the per-track `tkhd` atoms. A stale value in any one of them is enough
to mark the file as needing a correction, so the atoms cannot drift apart across runs —
which is what left imported files disagreeing with themselves: header `12:45:12`,
tracks `05:45:12`.

### Provenance

Before the first write, a file's original clock fields and filename are recorded once as
compact JSON in `XMP-xmpDM:LogComment`. That record is never overwritten and never read
back as a timestamp source — corrections always derive from the camera's own fields and
the filename. It exists so a future defect is recoverable outside the app, nothing more.

The record costs no exiftool call of its own: the tag is read with the fields the
correction already reads, and written in the same call the correction writes. A read or
write per file of its own runs the pipeline measurably slower, which the performance
snapshot rejects.

A namespace of jetlag's own would be tidier, but exiftool only writes tags it has a
definition for, so it would mean shipping an `-config` file and threading it through both
the Python wrapper and the Swift `jetlag-metadata` backend. `LogComment` is a free-form
string no camera writes and no correction reads, which is the whole requirement.

### `--timezone`

Always required for the fix-timestamps step: it declares where the footage was shot,
which rows 3, 4 and 6 need to label UTC and rows 5, 7 and 8 need to build an instant. The app mirrors
this single rule rather than deriving its own.

### `--force-timezone`

A confirmation gate, nothing more. Without it the pipeline refuses to relabel a file
whose `DateTimeOriginal` already carries an offset; with it the run proceeds. It does not
change the arithmetic.

This supersedes the behaviour where the flag kept the wall-clock time and replaced the
offset. That produced the right answer whenever the wall clock was right and only the
offset was stale, which is why it appeared to work, but it reached that answer by moving
the instant, and it fails on a card whose camera was still reading the previous country's
time.

### Idempotence

Relabelling is idempotent. Correcting a file twice with the same declared timezone
changes nothing the second time, because the first correction preserved the instant and
wrote the standard fields consistently. Where the instant was invented from a naive
source, the second run reads the fields the first run made consistent and reaches the
same answer.

`--time-offset` is excluded, and not as a caveat: it is a delta, so applying it twice
shifts twice. A run given `-2h` moves the instant back two hours every time it is run,
which is what the flag is for and what the user expects of it.

The existing idempotence test cannot show any of this: its fixture already carries a
zoned `DateTimeOriginal` and it runs with no declared timezone, so it exercises only the
pass-through path. The assertion that holds across the ranking is that **reprocessing a
corrected file yields what processing a pristine copy yields, for corrections that
relabel.**

## Done

`lib/timestamp_source.py` — `get_best_timestamp()` gains `_is_corroborated_utc()`, the
legal offset guard, and the reordering. Nothing else changed: the conversion the fix
relies on already existed in `get_all_timestamp_data()`, and the destructive QuickTime
rewrite stops on its own, because a preserved instant leaves that field already correct.

`fix-media-timestamp.py` — offset-bearing sources convert into a declared `--timezone`
(same instant, re-expressed) instead of being passed through unchanged, and
`--force-timezone` is a pure confirmation gate: a dry run always previews the proposed
relabel and emits `requires_force_timezone=true`; applying without the flag is refused.
The wall-clock rebuild the flag used to perform (which moved the instant) is deleted.

The durable per-field reference — field meanings, the UTC proof rules, the ranking —
now lives in `docs/timestamp-fields.md`.

## Not yet done

Each of these is separable, and none is needed for a correction to be right:

- `fix-media-timestamp.py` — a correction to a still loses its zone. `DateTimeOriginal`
  is written alone, and exiftool silently drops the zone from a value bound for binary
  EXIF rather than splitting it out (verified; see `timestamp-fields.md`). Stills need
  `OffsetTimeOriginal` written as its own tag alongside `DateTimeOriginal`.
- `media-pipeline.py` — the provided-versus-embedded mismatch still blocks, against the
  intent recorded in `time-correction-pipeline-step.md`, where it is informational and
  dry-run plus explicit apply is the safety gate.
- `scripts/AGENTS.md` — the hierarchy still lists the filename as the highest-priority
  source and states filenames are never modified. The filename is the source of truth for
  wall-clock time only where no corroborated UTC clock contradicts it, and
  `--update-filename-dates` renames files to match corrections.
- The app could surface the winning source from the diff table's existing
  `timestamp_source` field. No new dialog is needed: the choice is always decidable.

## Verification

Covered by `TestQuickTimeInstantVersusFilename` in `tests/test_timestamp_source.py` and
`test_camera_filename_with_quicktime_instant_converts` in
`tests/test_fix_media_timestamp_units.py`:

- A file with a filename-corroborated UTC clock and a contradicting camera filename
  corrects from the instant, converted into the declared zone.
- A file whose QuickTime date is years from its filename keeps the filename.
- A file with a zeroed QuickTime date keeps the filename.
- A file whose QuickTime date equals its filename keeps the filename.
- With no declared timezone the filename keeps winning, there being nothing to convert
  an instant into.
- Offsets at ±the legal bounds are instants; beyond them, and off the quarter hour, they
  are not.
- A file with no parseable filename date still uses its QuickTime date.

Fixtures for this need a real QuickTime date written explicitly: the template that
`create_test_video()` copies carries `0000:00:00`, which is why no test before these
could express a conflict between metadata and filename.

`TestProvenanceRecord` in `tests/test_fix_media_timestamp_units.py` covers the record:
written on the first correction, byte-identical after a later forced relabel, absent
after a dry run, and omitting the fields a file never carried.

`test_zoned_datetimeoriginal_converts_into_declared_zone` in
`tests/test_fix_media_timestamp_units.py` covers an offset-bearing `DateTimeOriginal`
converting into the declared zone rather than passing through unchanged.

`test_stale_movie_header_is_corrected_when_tracks_are_already_right` in
`tests/test_fix_media_timestamp.py` covers the movie header and the track atoms
agreeing after a correction.

`TestIdempotenceAcrossRanking` in `tests/test_fix_media_timestamp.py` covers, for each
source in the ranking: `original_epoch` equalling `corrected_epoch` unless
`--time-offset` was supplied (and, when it is, the corrected epoch landing exactly the
offset away), and reprocessing a corrected file yielding what processing a pristine
copy yields.

## Out of scope

- **Repairing already-corrected files** — files written by earlier runs carry a
  `DateTimeOriginal` from a timezone declared for a different trip, and a movie header
  inconsistent with their tracks. Their track atoms still hold the camera's instant, so
  they are recoverable, but as separate work rather than a jetlag feature.
- **Per-profile camera timezone** — would make filename-only files absolute by recording
  the zone the camera was set to. Only useful for cameras that write no metadata at all.
- **`.mp4` in the insta360 profile's `file_extensions`** — the X4 in 360 mode writes only
  `.insv`, so the entry can only ever match an Insta360 Studio export.
