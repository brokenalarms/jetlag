# Comedy night: Insta360 X6 and Sony A7V timestamps

Read `../timestamp-handoff.md` first: its "user's own words" and "principles" sections hold
for everything here. This spec is what a fresh agent needs to pick up the follow-ups from
the 2026-11-10 investigation of a backup report about the Comedy night footage
(6 Oct 2026, Perth, UTC+8). The investigation only read the files; the evidence below
comes from `exiftool` and `stat`, never from jetlag.

## The files

- Insta360 X6, firmware v1.1.7: `Videos/Source Video/Insta360/Ready/2026/10 - Sarah at Comedy Lounge/2026-10-06/`,
  seven `.insv`, 001–007, on the T9 (`/Volumes/T9`).
- Sony A7V: `Videos/Source Video/Sony A7V/Ready/2026/10 - Sarah at Comedy Lounge/2026-10-06/C0199.MP4`.
  Already corrected with `fix-media-timestamp --timezone +08:00 --apply` and moved with
  `organize-by-date` on 2026-11-10: nothing further to do.
- NAS mirror: `nas-rsync:/volume1/Backup/Mirror/Samsung 990/` (rsync-only key, no shell).
  It holds 001–003 and a partial 004 under their current names. The user runs the backup
  with their own rsync script; never start a backup.

## What the files hold

| Clip | Name's time | QuickTime CreateDate (UTC) | UTC in Perth | Name is in |
|---|---|---|---|---|
| 001 | 00:28:02 | 07:28:02 | 15:28:02 | UTC−7 |
| 002 | 04:58:47 | 11:58:47 | 19:58:47 | UTC−7 |
| 003 | 05:04:36 | 12:04:36 | 20:04:36 | UTC−7 |
| 004 | 05:05:05 | 12:05:05 | 20:05:05 | UTC−7 |
| 005 | 20:35:05 | 12:35:05 | 20:35:05 | Perth |
| 006 | 21:05:03 | 13:05:03 | 21:05:03 | Perth |
| 007 | 06:19:11 | 13:19:11 | 21:19:11 | UTC−7 |

- The UTC `CreateDate`, `MediaCreateDate` and `TrackCreateDate` are correct and continuous
  on all seven: 004–006 is one recording split every 30 minutes, and 004's 20:05 start is
  confirmed by the person who filmed it. `exiftool -fast2` misses these fields; read
  without it.
- The camera named 005 and 006 in Perth time and the rest in UTC−7. Jetlag renamed none
  of them.
- No clip carries anything jetlag writes (`Keys:CreationDate`, `DateTimeOriginal`, zone,
  XMP). Their birth times are the filename digits read as `+08:00`: the 10 Oct code's
  separate `SetFile` call landed while its metadata write was refused.

## 1. One source of truth for everything read from a file

This has been a core rule of the app from the start: every fact about a file comes from
its one exiftool read, which is cached (`exiftool.cache`), and every value derived from it
(the winning timestamp and its source, the file's zone, the camera's zone setting, the
filename's time, the date folder) is worked out once, by the hierarchy in
`lib/timestamps/sources.py`, and taken from there by every consumer.

The shape is declarative, and the correction already follows it: read the file once into
a list of current values (`read.py`, `CurrentTimestamps`); generate the list of expected
values (`plan.py`, `clock_targets` from the one clock-field table); compare the two, and the
difference is what will change (`needed_changes`, reported as `stale_fields` and
`stale_file_times`); apply writes exactly that difference. Everything else is a reading of
those two lists: a guard is a predicate over them (mixed zones compares current zones across
files; a future birth time checks one expected value against the read time), and the date
folder is one more expected value.

The read has held: `test_metadata_call_contract.py` counts it. The derivations have not,
because nothing enforces them, and the same decisions are made in parallel again, outside
the two lists:

| Decision | The hierarchy | Parallel copy |
|---|---|---|
| A file's zone | the winning source's zone | `extract_metadata_timezone`: the mixed-zone guard (`media_pipeline/preflight.py`), `read_current`'s `detected_tz`, `sources.py` |
| The camera's zone setting | `_RankingInputs` holds the UTC clock and the filename | `camera_zone_offset_for_file` gathers both again |
| A camera filename | `_camera_filename`'s `^(VID\|LRV\|IMG)_` pattern | the same pattern in `organize_by_date.py` |
| The date folder | the corrected time | `get_file_date_for_organization`: its own `DateTimeOriginal`, filename, modification time chain |
| The filename's time | parsed inside `get_best_timestamp` | parsed again in `fix_media_timestamp/read.py`, `describe.py`, `preflight.py` |

These are how the Comedy night went wrong in three places at once:

- **The mixed-zone guard** sees only zoned tags, so it never saw the X6 batch's two zones.
  Compared on the hierarchy's per-file zone, the UTC clock against each filename gives
  −07:00 for clips 001–004 and 007 and +08:00 for 005 and 006, and the import would have
  stopped as mixed. A file with no zone evidence adds nothing to the comparison; the
  guard says so rather than guessing.
- **The date folder** fell back to the file's modification time read in the Mac's zone:
  C0199's card modification time, NZ clock digits read in India (+05:30) where the import
  ran, filed it under 2026-10-07. It must come from the per-file result with the run's
  declared timezone, never from where the Mac is.
- **The correction and the guard** can disagree about a file, since each decides its zone
  separately.

Do this first, as a behaviour-preserving refactor held by the existing tests, deleting
each parallel copy. Then hold the derivations the way the call-count contract holds the
read: a test that fails when anything outside the hierarchy derives a file's time, zone,
filename time or date for itself, so the next refactor cannot reintroduce a copy. Then the ranking change below lands in one place and reaches the
correction, the guard and the date folder together. The standalone scripts
(`organize-by-date.sh` and the rest) keep working on their own: they build the same
per-file result from the same cached read.

## 2. Ranking: a camera filename against a UTC clock that contradicts it

The 10 Oct code (`def9e4a`), run dry on 001 with `--timezone +08:00`, took the filename
over the UTC `CreateDate` and planned to overwrite the correct UTC fields with a time
15 hours early. The current ranking (`docs/timestamp-fields.md`) still puts the filename
above a UTC clock the filename does not corroborate.

The user's rule, from `../timestamp-handoff.md`: the filename is "first source of truth for
wallclock local time, in the absence of disconfirming metadata (UTC)". Here the UTC clock
disconfirms the filename. #137 already prefers a QuickTime date over a contradicting camera
filename where the file shows the date to be an instant; find why that did not apply to
these clips, and whether the X6 clock fields meet the same test.

The user also said the hierarchy is per device and must not be replaced by a rule drawn
from two cameras. Propose the change to the user, with this table as the case, before
writing it. Pin it with a test built on an X6-shaped file: UTC clock fields, a filename in
another zone, `--timezone +08:00`. It must correct to the UTC instant in `+08:00`, rename
to the Perth time under `--update-filename-dates`, and never rewrite the UTC fields.

## 3. `.insv` from the X6 cannot be written

ExifTool 13.50 and 13.55 refuse every X6 clip. Without `-m` the refusal is a minor
error, `Terminator found in Meta with 41 bytes remaining`; with `-m` it is
`Corrupted Insta360 trailer`. The trailer's size and signature are valid, but the record table before them
is all zeros; X4 clips (NZ, firmware v1.9.21) write normally. The camera produced the
table, not jetlag: no write ever succeeded on these files, and exiftool writes to a
temporary file. The user is reporting it to ExifTool's author.

Since #256 a refused write fails the file, so an X6 import fails outright. The user's
decision: a write exiftool refuses as a corrupted Insta360 trailer is skipped with a
warning. The birth time, filename and date folder are still corrected (`.insv` reaches
Final Cut only through an Insta360 Studio export), and the row shows its own outcome
token rather than failing the file.

## 4. Fix Timestamps can be turned off in the app

The user expects the timestamp step to always run, but only Ingest and Organize are
always on (`PipelineStep.isAlwaysOn`); the workflow lets Fix Timestamps be tapped off.
C0199 was organized without a correction on 10 Oct, most likely through this. The
user's decision: the step becomes **Set Timestamps** and is always on. All the batch
checks move into one sequence with one output: `preflight-checks.md`.

## 5. Writes that rewrite a file without its birth time

On macOS any exiftool write gives the file a new birth time, so every write must carry
`FileCreateDate` (and therefore skip `-P`, see `scripts/AGENTS.md`). The timestamp step's
write does. `tag-media.sh` run on its own does not, so tagging a corrected library file
resets its birth time to its modification time. `ProvenanceStage` does not either, but it
only runs when the timestamp step is off (item 4). Pin it with a macOS test: tag a file
whose birth time is correct, and its birth time is unchanged.

## 6. Re-run the Insta360 clips

Once 1 to 3 have landed, run `fix-media-timestamp --timezone +08:00
--update-filename-dates --apply` on the seven clips where they sit, then `organize-by-date`
if a date changes. `media-pipeline` refuses a source inside its target, by design. This
needs the T9, so it runs on the user's Mac.

Before the rename, tell the user so their backup can either finish 004 under its current
name first, or run with rsync's `--fuzzy` (and a delayed `--delete`) so the renamed clips
transfer as deltas against the old names.

## Checks that only run on macOS

Linux CI tracks no birth time, so the birth-time tests are skipped there; the #247
regression (birth time clamped by `-P`) got past CI that way. Any change to
timestamps needs `scripts/tests` run on macOS before it merges, and the macOS app tests if
anything under `macos/` or `scripts/` changed.
