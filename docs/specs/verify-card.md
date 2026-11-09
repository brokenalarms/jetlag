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
  the file's original name. See "Provenance".
- **No recorded location**: where a file lives is never stored in it. Files are
  regrouped and moved after import (an import without a group, then moved into
  one), so any stored path goes stale; a copy is found by its name wherever it is.

The content hash (see "Deep check") is jetlag's own sha256 of the file's data portion
(see "What is hashed"), not exiftool's `ImageDataHash`: a byte range can be hashed with
standard tools on a `host:/path` location's host, which has no exiftool.

## Provenance

Recorded once, on the first write jetlag makes to a file, never overwritten, and
written in the same exiftool call as the correction — no read or write of its own.

| Property | Value |
|---|---|
| `XMP-xmpMM:PreservedFileName` | the name the file had on the card |
| `XMP-jetlag:OriginalDateTimeOriginal` … `OriginalCreationDate` | each clock field as it was before jetlag's first write, for recovery outside the app |
| `XMP-jetlag:ContentSHA256`, `XMP-jetlag:ContentBytes` | sha256 and size of the file's content without its metadata (the data portion, see "What is hashed"). Not written at import: added later by the deep check, as a cache (see "Hash cache") |

`jetlag` is a custom XMP namespace (`http://ns.jetlag.app/1.0/`) declared in
`scripts/lib/exiftool-jetlag.config`. Exiftool only writes tags it has a definition
for, so both metadata backends load that config. One property per value, so each is
readable directly (`exiftool -XMP-jetlag:OriginalCreateDate`) with nothing to parse.

Files imported before this namespace carry a JSON record in `XMP-xmpDM:LogComment`
instead. That record also counts as "already recorded", because those files' clock
fields are already corrected and recording them now would store corrected values as
originals. Verify reads its `filename` key as the original name.

### No hash at import

Ingest copies with `shutil.copy2` and computes no hash. Hashing during the copy would
add its time to every import (unless overlapped on a second thread) for a check most
runs never use, and it would only record the bytes as read, so it could not catch a bad
card read. The deep check hashes the card itself instead, at the time the user asks.

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

A file's copy on a backup location is looked for anywhere under that location's root,
so it is found wherever it has been grouped or moved since import. A sync tool's archive
of deleted items (`#recycle`, `@eaDir`, `.stversions`) is excluded: a copy there is on
its way out, not backed up.

The default check never reads a location over the network. A local one is walked; a
remote one is listed with `rsync --list-only --recursive` (path, size, mtime), which the
remote host produces itself in seconds. Header reads for footage size and provenance happen on a
local copy; a remote copy with the same path, size and mtime shares its result.

### Local or network

Whether a location is local or network is detected on every run, never configured or
stored: the same root can be a USB drive one day and an SMB mount the next.

- A `host:/path` root is remote by its syntax and is reached over ssh.
- Any other root is local only if its volume's filesystem type is on an allowlist
  (`apfs`, `hfs`, `exfat`, `msdos`, `ntfs`; on Linux `ext4`, `xfs`, `btrfs`), the mount
  is flagged local (`MNT_LOCAL` from `statfs`, `volumeIsLocalKey` in the app), and the
  volume is not a disk image whose backing file is itself on a network volume.
- `smbfs`, `afpfs`, `nfs` and `webdav` mounts are network mounts, however the share
  appears under `/Volumes` — unless the mount's server (`f_mntfromname`, e.g.
  `//user@127.0.0.1/Media`) resolves to this machine. A share this machine (or a VM on
  it) serves to itself over loopback is a local disk, so it is local.
- FUSE mounts (`macfuse`, `fuse.*`) and unrecognised types cannot say where their data
  lives, so they are assumed to be network. Allowlisting local types means a misread
  only ever moves a location from "Verify hashes" to "Include network locations"; it
  never changes the default verdict.

Each location on the Verify screen carries a small "Local" or "Network" label (a
`host:/path` root is "Network"), so it is clear which locations each deep-check
checkbox covers. The label is information only: no location gets a warning or note
of its own.

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

**Verdict per location**: matched with equal total size (an untouched copy) or equal
footage size (a jetlag-written copy); otherwise missing or footage differs. Two
matches on one location are listed as duplicates for the user to resolve.

## Verify screen

Laid out like Workflow: the source folder, then one group per configured backup
location showing its destination folder, each with a toggle to include it in this
check. Below them "Include companion files" (defaulting to the workflow's
copy-companion setting) and Run. The default check is read-only, and the deep check
writes only the hash cache, which changes no content, so there is no dry-run/apply
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

## Deep check

Two checkboxes on the Verify screen, both off by default:

- ☐ **Verify hashes** — every matched copy on a "Local" location has its content
  hashed and compared with the card file's.
  - ☐ **Include network locations (slow)** — enabled only while "Verify hashes" is
    ticked; adds the "Network" locations.

This is the only place jetlag hashes content. It catches a bad card read at import,
damage to a copy since (bit rot, a bad sync), and a copy cut short with its size
intact.

### Reference hash

For each card file the reference is, in order:

1. the `XMP-jetlag:ContentSHA256` recorded on any of its matched copies, when that
   copy's `XMP-jetlag:ContentBytes` equals the card file's footage size. The card is
   not read. A recorded hash is only ever written after it matched the card (see
   "Hash cache"), so it stands in for the card.
2. otherwise, the card file's content hashed from the card. The card is only read,
   so a read-only card works.

Two copies recording different hashes for one card file are listed as "Recorded
hashes disagree", and the card is hashed to settle which is right.

### Hashing a copy

How a copy is hashed is not shown to the user:

- a local copy is read directly.
- a `host:/path` copy is hashed on its host over ssh
  (`tail -c +OFFSET file | head -c LEN | sha256sum`), so only the digest crosses the
  network. Offsets come from a matching local copy's box headers; without one, the
  box headers are read on the host with small `dd` reads.
- a network-mounted copy is hashed by reading its content across the network.

A copy whose hash differs from the reference is listed as "Hash mismatch" on that
location — it says what was found, not why. A copy is never passed on a recorded hash
alone: every ticked copy is hashed on every run.

### Hash cache

When a copy on a "Local" location hashes equal to a reference read from the card and
records no hash yet, `XMP-jetlag:ContentSHA256` and `XMP-jetlag:ContentBytes` are
written into it, once, never overwritten. A later run then takes the reference from
the copy and does not read the card again, which is the slow part (100–300 MB/s
against a local disk's GB/s).

- Network copies are not written: a network-mounted write rewrites the whole file
  across the network, and a `host:/path` host has no exiftool. They receive the cache
  only if a sync tool mirrors a local copy onto them.
- A copy that mismatches, or whose card file had disagreeing recorded hashes, is not
  written.
- The write is metadata only and leaves the content, and so the hash, unchanged (the
  phase 2 regression test). It does change the file's size and mtime, so a sync tool
  mirroring that location copies the file again on its next run.
- The card is never written.

### What is hashed

The hash always covers the file's data portion and never its metadata, which jetlag
and other tools rewrite. The data portion is the same bytes on the card and on every
copy, however its metadata has changed, so one hash compares them all. For each format
it is located from the file's own structure with small header reads, like footage size:

| Format | Data portion |
|---|---|
| QuickTime family (`.mp4 .mov .insv`, recognised by its first box as `scripts/lib/footage.py` does) | each `mdat` payload plus any trailer after the last box |
| HEIF (`.hif .heic`) | each `mdat` payload |
| JPEG (`.jpg .insp`) | from the first start-of-scan marker to the end of the file, so images and camera trailers appended after the main image are included |
| TIFF-based RAW (`.arw .dng`) | the strips or tiles of the full-size image |
| Fujifilm `.raf` | the raw data block the RAF header points to |

A copy on a `host:/path` location is hashed over the same range, with offsets from a
matching local copy or read on the host with small `dd` reads. A format not in the
table is not hashed and is reported "Not hashable", never passed or failed. Before
phase 7, the regression test from phase 2 is extended to each photo profile's format:
its data portion is unchanged by tag + fix-timestamp.

## Phases

1. Provenance moves into the `jetlag` XMP namespace and `PreservedFileName`, with the
   config loaded by both metadata backends.
2. Footage-size reader for QuickTime-family files, with a regression test that footage
   size and hash are unchanged by tag + fix-timestamp on each profile's format.
3. Provenance on every moved file.
4. `verify-card.py`: source scan, location listings, matching, JSONL verdicts.
5. Verify screen in the app; backup-location configuration screen.
6. `archive-source` delete mode accepts only verified or user-accepted files.
7. Local/network detection and label per location; "Verify hashes" and "Include
   network locations (slow)": reference hash from the hash cache or the card, ssh
   copies hashed on their host, hash cache written to matching local copies.
