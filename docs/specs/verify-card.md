# Verify card

## Goal

Before a card is wiped, check that every file on it is at its expected place on each
backup location the user has enabled — however many they have configured. A file that
is not provably on every enabled location is listed for the user to investigate.
Nothing is ever passed on a guess.

## Why a byte comparison cannot work

Any exiftool write rebuilds a QuickTime file: every top-level box except `mdat` is
written first, then `mdat` is copied after them with the chunk offsets rewritten. An
Insta360 file goes from `ftyp wide mdat moov <trailer>` on the card to
`ftyp moov uuid(XMP) mdat <trailer>` after import. The footage bytes are identical but
almost every byte offset differs, so a whole-file hash or `cmp` against the card
always fails. Files jetlag never wrote to keep the camera's layout and match exactly.

Timezone corrections can also rename a file (`VID_20250619_042028_00_004` becomes
`VID_20250619_072028_00_004`), so the card name does not find the copy either.

## What identifies a copy

- **Footage size**: the payload size of `mdat` plus any trailer after it. Read from
  the top-level box headers alone — a handful of reads of 8–16 bytes per file, no
  footage read. An imported copy has exactly the card file's footage size and a few
  KB more metadata.
- **Provenance in the file**: jetlag records, in the same write as its other metadata,
  the file's original name and where it put the file. See "Provenance".

Exiftool's `ImageDataHash` is not used: it hashes the video and audio tracks one at a
time via the `moov` sample tables, which on a card come after the footage, so it can
never be computed while the import streams the file, only by a second full read.

## Provenance

Recorded once, on the first write jetlag makes to a file, never overwritten, and
written in the same exiftool call as the correction — no read or write of its own.

| Property | Value |
|---|---|
| `XMP-xmpMM:PreservedFileName` | the name the file had on the card |
| `XMP-jetlag:OriginalDateTimeOriginal` … `OriginalCreationDate` | each clock field as it was before jetlag's first write, for recovery outside the app |
| `XMP-jetlag:Destination` | the full path organize moved the file to |
| `XMP-jetlag:FootageSHA256`, `XMP-jetlag:FootageBytes` | hash and size of `mdat` + trailer, computed while ingest copies the file |

`jetlag` is a custom XMP namespace (`http://ns.jetlag.app/1.0/`) declared in
`scripts/lib/exiftool-jetlag.config`. Exiftool only writes tags it has a definition
for, so both metadata backends load that config. One property per value, so each is
readable directly (`exiftool -XMP-jetlag:Destination`) with nothing to parse.

Files imported before this namespace carry a JSON record in `XMP-xmpDM:LogComment`
instead. That record also counts as "already recorded", because those files' clock
fields are already corrected and recording them now would store corrected values as
originals. Verify reads its `filename` key as the original name.

### Footage hash during ingest

Ingest replaces `shutil.copy2` with a copy loop that feeds the `mdat` payload and any
trailer into `hashlib.sha256` as the bytes pass, then applies `copystat`. Card reads
run at 100–300 MB/s and sha256 at several GB/s, so the copy stays at card speed; the
performance gate confirms it. The pipeline carries the hash to the fix-timestamp write.

The hash is never part of the default verdict. It backs an opt-in deep check that
reads the local imported copy only — never the card or a network location — and catches
damage to that copy after import. It cannot catch a bad card read, which is baked into
the hash.

### Provenance on every file

Provenance is written to every file jetlag moves, including one no other step writes
to. That costs an exiftool rewrite of the working copy (same volume) for that file.

## Backup locations

The user adds backup locations on a configuration screen of their own; there can be
any number. Every location is a mirror of the imported library; none is primary. A
location is a name and a root, in a top-level `backups:` mapping in
`media-profiles.yaml`, keyed by name — for example:

```yaml
backups:
  T9:
    path: /Volumes/T9/Videos/Source Video
  NAS:
    path: nas-rsync:/volume1/Backup/Mirror/T9/Videos/Source Video
```

A file's expected path on a backup location is its recorded `Destination` with the root
of the location it was written under replaced by this location's root. A copy anywhere else —
including a sync tool's archive of deleted items — does not count; when the expected
path is missing, a same-named file elsewhere in the listing is shown as a hint.

Locations are never read over the network. A local one is walked; a remote one is
listed with `rsync --list-only --recursive` (path, size, mtime), which the remote
host produces itself in seconds. Header reads for footage size and provenance happen on a
local copy; a remote copy with the same path, size and mtime shares its result.

## The check

**Source** is a folder the user picks, usually the card root — not a profile, because
one card holds files from several cameras and profiles can be deleted.

Under the source, files are sorted by lists the check owns (seeded once from the
profiles' extensions, then independent of them):

| File | Verdict |
|---|---|
| media extension (`.mp4 .mov .insv .insp .jpg .arw .dng .mxf` …) | must be on every enabled location |
| companion extension (`.lrv .thm .lrf`, Sony clip `.XML`) | required only with "Include companion files" ticked |
| under an ignored path (`MISC/` — Insta360's 468 KB `.insv` stubs that copy real clip names and are not video) | not checked |
| hidden (`.dcf_reserved_space`, `._*`) | not checked |
| anything else (camera databases, `.BIN`) | not checked, counted in the summary |

Archived card folders (`DCIM - copied <date>`) are under the source and checked like
any other.

**Match** a card file to a file on a location when that file has the same name, or its
`PreservedFileName` equals the card name. Nothing looser counts.

**Verdict per location**: matched at the expected path with equal total size (an
untouched copy) or equal footage size (a jetlag-written copy); otherwise missing,
footage differs, or not at expected path.

## Verify screen

Laid out like Workflow: the source folder, then one group per configured backup
location showing its destination folder, each with a toggle to include it in this
check. Below them "Include companion files" (defaulting to the workflow's
copy-companion setting) and Run. The check is read-only, so there is no dry-run/apply
split.

The right-hand panel reuses the table machinery with a row type of its own, not
`DiffTableRow`:

- a summary line that is always shown, so an empty table reads as all clear rather
  than as a check that found nothing: "203 files on card · 195 on every enabled location · 8 need
  attention · 41 not checked (.lrv, .thm, MISC/)"
- one status column per enabled location
- for each unmatched clip: duration and size, whether its neighbouring clip numbers
  were imported, and whether it opens (`ffprobe` returning no duration means a broken
  recording)
- "Show matched", off by default

## Phases

1. Provenance moves into the `jetlag` XMP namespace and `PreservedFileName`, with the
   config loaded by both metadata backends.
2. Footage-size reader for QuickTime-family files, with a regression test that footage
   size and hash are unchanged by tag + fix-timestamp on each profile's format.
3. Footage hash during ingest; `Destination` and the hash join the provenance write;
   provenance on every moved file.
4. `verify-card.py`: source scan, location listings, matching, JSONL verdicts.
5. Verify screen in the app; backup-location configuration screen.
6. `archive-source` delete mode accepts only verified or user-accepted files.
7. Opt-in deep check against the footage hash.
