# ExifTool 13.64 for Insta360 X6

## Constraint

Insta360 X6 `.insv` clips (firmware v1.1.7) need **ExifTool 13.64 or later** to
have any metadata written. The app vendors 13.50 (`scripts/tools/`), and 13.63
is the latest public release, so neither can write them. Bump the vendored copy
once 13.64 is published.

## Why older versions fail

Phil Harvey's diagnosis of a sample X6 clip:

- The X6 puts its Insta360 trailer inside a terminating `inst` box. ExifTool up to
  13.63 doesn't expect that and reports `Corrupted Insta360 trailer`. 13.64 reads
  the trailer inside the box.
- The X6 writes its `meta` box as a full box rather than a plain box, so it looks
  empty to ExifTool: `[minor] Terminator found in Meta with 41 bytes remaining`.
  13.64 repairs this, **but only when `-m` is passed**.
- The file holds many `udta` boxes with no metadata in them. ExifTool deletes
  these when it rewrites the file.

## What the upgrade involves

- Replace `scripts/tools/exiftool` and `scripts/tools/lib/` with the 13.64
  distribution, and update the version in `scripts/tools/README`.
- `ExifTool.write_tags` already retries a refusal made only of minor errors once
  with `-m`, which is the path that triggers 13.64's `meta` repair. No change is
  expected there. Check it against a real X6 clip.
- Check that the footage hash (`lib/footage.py`) of an X6 clip matches before and
  after a write. The trailer now sits inside an `inst` box, which the box walk
  stops at and counts as trailer. The removed `udta` boxes aren't footage.
- X6 clips stop reporting `metadata_skipped`. The `Insta360TrailerCorrupted` path
  stays as the fallback for an older `exiftool` on `PATH` (CI's Ubuntu package).
- Rework the tests and notes that describe X6 clips as unwritable:
  `TestInsta360ClipWhoseMetadataCannotBeWritten`,
  `create_insv_with_corrupted_trailer` / `exiftool_refuses_corrupted_insta360_trailer`
  and their "the app ships 13.50" skip reasons, and the X6 note in
  `scripts/AGENTS.md`. Add a fixture with the X6 layout (`meta` full box, empty
  `udta`, trailer in a terminating `inst` box) that 13.64 writes with `-m`.
