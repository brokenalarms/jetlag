# Comedy night: Insta360 X6 and Sony A7V timestamps

Read `timestamp-handoff.md` first: its "user's own words" and "principles" sections hold
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

## 1. Ranking: a camera filename against a UTC clock that contradicts it

The 10 Oct code (`def9e4a`), run dry on 001 with `--timezone +08:00`, took the filename
over the UTC `CreateDate` and planned to overwrite the correct UTC fields with a time
15 hours early. The current ranking (`docs/timestamp-fields.md`) still puts the filename
above a UTC clock the filename does not corroborate.

The user's rule, from `timestamp-handoff.md`: the filename is "first source of truth for
wallclock local time, in the absence of disconfirming metadata (UTC)". Here the UTC clock
disconfirms the filename. #137 already prefers a QuickTime date over a contradicting camera
filename where the file shows the date to be an instant; find why that did not apply to
these clips, and whether the X6 clock fields meet the same test.

The user also said the hierarchy is per device and must not be replaced by a rule drawn
from two cameras. Propose the change to the user, with this table as the case, before
writing it. Pin it with a test built on an X6-shaped file: UTC clock fields, a filename in
another zone, `--timezone +08:00`. It must correct to the UTC instant in `+08:00`, rename
to the Perth time under `--update-filename-dates`, and never rewrite the UTC fields.

## 2. `.insv` from the X6 cannot be written

ExifTool 13.50 and 13.55 refuse every X6 clip: `Corrupted Insta360 trailer`, with or
without `-m`. The trailer's size and signature are valid, but the record table before them
is all zeros; X4 clips (NZ, firmware v1.9.21) write normally. The camera produced the
table, not jetlag: no write ever succeeded on these files, and exiftool writes to a
temporary file. The user is reporting it to ExifTool's author.

Since #256 a refused write fails the file, so an X6 import fails outright. Decide with the
user whether X6 `.insv` skips the metadata write (the birth time, filename and date folder
are still corrected; `.insv` reaches Final Cut only through an Insta360 Studio export),
and how that shows in the app.

## 3. The organize step dates a file by the Mac's zone

When the run carries no corrected time, `get_file_date_for_organization()` falls back to
the file's modification time read in the Mac's current zone. C0199 was filed under
2026-10-07 this way: its card modification time, NZ clock digits read in India (+05:30),
where the import ran. The date folder must come from the same ranking the timestamp step
uses, with the run's declared timezone, never from where the Mac is.

## 4. Fix Timestamps can be turned off in the app

The user expects the timestamp step to always run, but only Ingest and Organize are
always on (`PipelineStep.isAlwaysOn`); the workflow lets Fix Timestamps be tapped off.
C0199 was organized without a correction on 10 Oct, most likely through this. Confirm the
intent with the user before changing it.

## 5. Writes that rewrite a file without its birth time

On macOS any exiftool write gives the file a new birth time, so every write must carry
`FileCreateDate` (and therefore skip `-P`, see `scripts/AGENTS.md`). The timestamp step's
write does. `tag-media.sh` run on its own does not, so tagging a corrected library file
resets its birth time to its modification time. `ProvenanceStage` does not either, but it
only runs when the timestamp step is off (item 4). Pin it with a macOS test: tag a file
whose birth time is correct, and its birth time is unchanged.

## 6. A birth time in the future

`--preserve-wallclock` (shooting clock digits in the Mac's zone) and `--time-offset` can
make the corrected birth time a later instant than the shot. Applied soon enough after
shooting, from a Mac west of the shooting zone, the birth time lands in the future and the
write's modification time is earlier than it: an invalid file. Jetlag never sets the
modification time, so the birth time must not be written in that case; report the file
instead. Confirm the reporting with the user.

## 7. Re-run the Insta360 clips

Once 1 and 2 have landed, run `fix-media-timestamp --timezone +08:00
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
