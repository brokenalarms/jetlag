# Timestamp fields — truth table

Source of truth for every timestamp field jetlag touches: what it is, what its values
can mean, whether that meaning is guaranteed, and where it ranks. Change behaviour only
in agreement with this table, and change this table when behaviour changes.

The ranking rules and the reasoning behind them live in
`specs/completed/timestamp-source-of-truth.md`; the durable per-field facts live here.

## Vocabulary

- **wall clock** — the digits a human read at the scene (`07:35:32`).
- **zone** — the `±HH:MM` label saying which timezone those digits belong to.
- **UTC / the actual time** — the moment itself, independent of zone. Only
  `--time-offset` may ever move it; every other operation relabels.
- **naive** — a value with digits but no zone. Usable only with a declared
  `--timezone`, whose zone the digits are assumed to belong to.

## The fields

| Field (exiftool name) | Where it lives | Stored as | Zone semantics per spec | Reality | jetlag reads | jetlag writes |
|---|---|---|---|---|---|---|
| `Keys:CreationDate` | `com.apple.quicktime.creationdate` (Keys metadata) | text | self-describing: `Z` = digits are UTC; `±HH:MM` = digits are local in that zone; bare = naive | iPhone writes zoned local; trustworthy when zoned. FCP keys off this field | yes | yes — zoned local |
| `DateTimeOriginal` | `XMP-exif` on video (where a bare exiftool write lands); UserData/`IDIT` natively; binary EXIF on stills | text | XMP is ISO-8601, zone may ride in the value; **binary EXIF is exactly 19 chars — no zone possible** (see `OffsetTimeOriginal`) | camera-written: local + camera's zone setting; jetlag-written: local + declared zone | yes | yes |
| `OffsetTimeOriginal` | binary EXIF (stills), added in EXIF 2.31 | text `±HH:MM` | **always and only the zone** of `DateTimeOriginal`'s digits — never an instruction to shift time | cameras that set it are stating their zone setting | yes — completes a bare `DateTimeOriginal` into a zoned value at read time | yes — alongside `DateTimeOriginal`, same write |
| `QuickTime:CreateDate`, `ModifyDate` | `mvhd` movie header atom | integer, seconds since 1904 | UTC by specification | devices vary; ecosystem docs (exiftool, PhotoPrism #1388) report local-time writers. Not observed on our devices — X4 writes true UTC. **Proof required per file** (below) | yes | yes — UTC, computed in Python, written raw |
| `QuickTime:MediaCreateDate`, `MediaModifyDate` | `mdhd` per-track atom | integer, seconds since 1904 | UTC by specification | as above | yes | yes — UTC, written with the header and track atoms in one call |
| `TrackCreateDate`, `TrackModifyDate` | `tkhd` per-track atom | integer, seconds since 1904 | UTC by specification | written since corrections reached the track atoms; the provenance record, not these atoms, is what makes a damaged file recoverable | yes | yes — UTC, written with the header and media atoms in one call |
| filename digits | the name itself | text | **never zoned** — no filename pattern carries a zone | the camera's own wall-clock display; first truth for local time absent disconfirming metadata | yes | renamed by `--update-filename-dates` |
| file birth / mtime | filesystem | epoch | filesystem-dependent | changes with copies; last resort | yes (macOS) | yes |

## Policies

### exiftool's `QuickTimeUTC` option is never used, read or write

The option makes exiftool convert QuickTime dates between UTC and *the machine's
local zone* at the API boundary — a global assumption applied invisibly to values
whose UTC-ness is actually per-file. It moves the logic out of our system and makes
it opaque which values we converted and which exiftool did.

History: commit `2385ede` added `-api QuickTimeUTC=1` to a write path that already
computed UTC in Python — exiftool then treated that UTC value as local and shifted it
a second time. It was removed again. All conversions happen in our code; strings at
the exiftool boundary are raw field contents.

### A UTC-specified field is corroborated UTC only when the file shows it

The QuickTime clock atoms are UTC by specification, but a device may write local
digits into them and a clock may simply be wrong. We never try to detect that
directly; the file's own wall clock — the filename — either corroborates the field
or it doesn't:

| Evidence | Conclusion |
|---|---|
| `filename − clock` is a legal, nonzero zone offset | **corroborated UTC** — and the difference **is the camera's zone setting** at shoot time |
| `filename − clock` is zero | camera at UTC+0 and local-in-UTC-field look identical — uncorroborated |
| `filename − clock` is not a legal offset | broken clock (e.g. battery reset); the filename wins |
| no filename digits | uncorroborated — the field keeps its specified meaning, UTC, but nothing in the file backs it |

A zoned tag is never used to corroborate the clock: a camera-written zoned tag comes
from the same clock plus the zone setting, so the two always agree, and where they
disagree the zoned tag was written by something other than the camera. Zoned tags
simply rank above the clock.

The filename side of the subtraction is always local wall clock — the check works
*because* the filename is never UTC. A legal zone offset is −12:00 to +14:00 in
15-minute steps.

### Ranking (first match wins)

| # | Source | Needs declared `--timezone`? |
|---|---|---|
| 1 | `DateTimeOriginal` with zone — inline, **or** completed by `OffsetTimeOriginal` | no (self-contained); declared zone converts it, gated by `--force-timezone` |
| 2 | `Keys:CreationDate` with zone | no — same |
| 3 | `Keys:CreationDate` ending `Z` | yes — UTC can't be labelled without one |
| 4 | clock (`MediaCreateDate`), corroborated UTC | yes — same |
| 5 | filename digits (camera patterns) | yes — digits are naive |
| 6 | clock (`MediaCreateDate`), uncorroborated — UTC by specification only | yes |
| 7 | `DateTimeOriginal` bare **and** no `OffsetTimeOriginal`; bare `Keys:CreationDate` ranks here too | yes |
| 8 | file birth / mtime | yes |

Zoned tags rank first: they carry both the digits and their zone. UTC sources need the
declared zone to be labelled, and the clock ranks below the filename only where the
filename fails to corroborate it. An uncorroborated clock still outranks the bare
tags: its specification says what its digits mean, a bare tag's does not. Read priority is separate from what other apps
consume: corrections rewrite **all** clock fields, so FCP reads a corrected
`Keys:CreationDate` no matter which source won.

### `--timezone`, `--force-timezone`, `--time-offset`

- `--timezone` declares where the footage was shot. For UTC sources (rows 3, 4, 6) it is the
  display zone; for naive sources (rows 5, 7, 8) it is the zone the digits are assumed to
  belong to.
- A file whose winning source already carries a zone is never relabelled to a
  different declared zone without `--force-timezone`. Dry runs always preview the
  proposed relabel and emit `requires_force_timezone=true`; applying without the flag
  is refused. Relabelling converts — same UTC, new wall clock — it never keeps the
  digits and swaps the zone suffix.
- `--time-offset` is the only operation that moves the actual time, and it is a delta:
  running it twice shifts twice, by design.

### `OffsetTimeOriginal` completes a bare `DateTimeOriginal` on read

A still's `DateTimeOriginal` can never carry an inline zone — binary EXIF gives it
exactly 19 characters — so `OffsetTimeOriginal` is the only zone it can have. On read,
a bare `DateTimeOriginal` plus a legal `±HH:MM` `OffsetTimeOriginal` are joined into
one zoned value, which lifts the file from row 7 to row 1. A bare `DateTimeOriginal`
with no `OffsetTimeOriginal`, or with an unparseable one, stays at row 7.

### Writing a zoned `DateTimeOriginal` to a still silently drops the zone

Verified against the vendored exiftool 13.50, not assumed. Writing
`-DateTimeOriginal="2024:03:15 08:30:00+09:00"` to a JPEG stores only the bare digits:
exiftool does **not** split the zone out into `OffsetTimeOriginal`, does not create
that tag, and prints no warning — it reports success and discards what will not fit
the 19-byte field.

```
$ exiftool -overwrite_original -DateTimeOriginal="2024:03:15 08:30:00+09:00" still.jpg
    1 image files updated
$ exiftool -s -G -time:all -OffsetTimeOriginal still.jpg
[EXIF]          DateTimeOriginal                : 2024:03:15 08:30:00
```

(`OffsetTimeOriginal` absent — the tag is never touched. Writing it explicitly does
round-trip: `-OffsetTimeOriginal="+09:00"` reads back intact.)

jetlag therefore writes `OffsetTimeOriginal` as its own tag in the same call as
`DateTimeOriginal`, so the zone survives on a still; on a video the same write is
harmless, exiftool keeping the zone inline in XMP and dropping the offset tag.

### Caveat: metadata previously written with a wrong declared zone

Converting preserves the file's UTC — which preserves the *error* if an earlier run
stamped the file with a wrong declared zone (its UTC was derived from that wrong
label). For those files the filename digits remain the truth and
`--infer-from-filename` or the track-atom recovery path is the tool, not
`--force-timezone`.

## External references

- exiftool QuickTime tags: https://exiftool.sourceforge.net/TagNames/QuickTime.html
- PhotoPrism #1388: phone videos store UTC in QuickTime fields while paired photos
  carry local time; importers that ignore this show hours-off timestamps. Their fix —
  a global assume-UTC option — is the assumption jetlag replaces with per-file proof.
