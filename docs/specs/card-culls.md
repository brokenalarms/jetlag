# Card culls

Read `completed/verify-card.md` first: this extends its check and its verdicts.

## Goal

A card is wiped once Verify shows that everything on it is safe on every enabled backup
location. Backups run whenever a location is reachable (the NAS when there is wifi, a
drive when it is plugged in), and culling in Lightroom happens whenever the user gets
to it. So a culled clip is still on the card, `missing` on at least one location and
possibly on all of them, and today it blocks the card forever: the only way past it is
to accept it again on every run.

A cull can't be recognised from the file afterwards: nothing about its name, or about
which locations hold a copy, says whether it was culled. But Jetlag knows exactly which
files it imported and where it put them. A file Jetlag imported that is no longer on
the location it was imported to has been culled there, whatever the other locations
hold. A file Jetlag didn't import has no such history, so it is checked exactly as it is
today.

The end result is one verdict for the whole card, safe to wipe or not. It doesn't give
permission to delete particular files.

## The import record

Every file the import step copies is recorded as it is copied, in `imports.jsonl` beside
`media-profiles.yaml` in the app's Application Support folder. It is the user's data,
like the profiles file, and a launch never overwrites it. One line per copied file:

| Field | Value |
|---|---|
| `card_name` | the file's name on the card |
| `data_bytes` | the card file's data portion size, as `verify-card.md` defines it per format |
| `location_root` | the root of the enabled backup location the destination is under |
| `imported_at` | when it was copied, ISO 8601 with offset |
| `destination` | the path it was copied to, for the user's reference only; never matched on, because files are regrouped and moved after import |

The data size comes from header reads on the card file, a handful of small reads per
file, taken while the file is being copied. A format with no data-portion reader
records its total size, which only matches a card file that Jetlag never wrote.

A destination that isn't under any enabled location still records `card_name`,
`data_bytes` and `imported_at`, with no `location_root`. Such a file has nowhere to be
culled from, so it is checked as it is today.

Only files the import actually copied are recorded. A file it skipped because it was
already there, a companion it wasn't asked to copy, and anything under the Verify
ignore paths are not recorded.

Records are never pruned. Once a card is wiped its records match nothing, and each one
is a few hundred bytes.

## Verify

`verify-card` takes the record as an argument (`--imports PATH`), in the same way it
takes `--location`; it never reads the app's folder. A standalone run without it
behaves as it does today.

A card file is **imported** when a record matches it: its name equals `card_name`, its
data portion size equals `data_bytes`, and the record names a `location_root` that is an
enabled location in this run. Both the name and the size are needed, because Sony
restarts `C0001` after a counter reset and two cards can hold different clips under one
name. If several records match, the most recent one is used.

For an imported file, that location's verdict decides:

| Verdict on the import location | Meaning | The file |
|---|---|---|
| `matched` | still in the library, wherever it was moved | must be `matched` on every other enabled location, as today |
| `missing` | culled | **culled**: no longer counts against the card |
| anything else (`duplicate`, `data_differs`, `unreachable`, ...) | can't tell | needs attention, as today |

A culled file's other per-location verdicts are left as found and shown, but don't
count. Copies that are still there don't matter, so a mirror that later drops them
changes nothing.

A card file with no matching record is **not imported by Jetlag**. That covers files
copied by hand, imports from before this record existed, and imports to a location
that is disabled in this run. It gets no new treatment: it must be `matched` on every
enabled location or it needs attention, exactly as today.

`scripts/lib/verify-card-schema.yaml` gains a file-level `origin` (`imported` or
`unknown`) and `culled: true`.

### What this can't tell apart

A file that disappeared from the import location by accident (a drive failing, a sync
tool deleting from the wrong side, a bad rescue copy) looks exactly like a cull. Nothing
records how a file left, and the Trash can't settle it because it can be emptied at any
point. Verify shows the culled count per import location ("47 culled from T9"), so a
number much larger than the user remembers culling is visible before the card is
wiped. Expanding it lists each culled file.

## Verify screen

- Culled files are hidden like matched ones, behind "Show culled" (off by default).
- Files not imported by Jetlag that need attention are marked "Not imported by Jetlag",
  so it is clear why they can't be culled.
- The summary line: "203 files on card - 180 on every enabled location - 15 culled from
  T9 - 8 need attention - 41 not checked (.lrv, .thm, MISC/)".

## Safe to wipe

Verify ends with one verdict for the card:

- **Safe to wipe** when every checked file is either matched on every enabled location
  or culled. With "Verify hashes" ticked, every matched copy in scope must also hash
  equal.
- **Not safe to wipe** otherwise, with the number of files that need attention.

The verdict names the locations it was checked against ("on T9 and NAS"), because safe
only means as safe as the locations that were enabled. Disabling a location for one run
narrows what the verdict claims, and the verdict says so; a file whose import location
is disabled can't be culled in that run.

Jetlag never wipes the card; the user formats it in the camera. `archive-source --action
delete` treats a culled file as cleared, like a matched or accepted one, so that path
can never disagree with the card verdict.

## Out of scope

- Files imported before this record existed. They show as not imported by Jetlag. A
  record can't be rebuilt for them afterwards, because the culled ones are no longer
  there to read.
- Deletions mirrored to a backup location after the card is gone (a `--delete` push to
  the NAS, for example). That is the mirror tool's problem.

## Phases

1. The import step writes `imports.jsonl`, with the data size read from the card file.
   Tests: one record per copied file; none for skipped, uncopied-companion or ignored
   files; no `location_root` when the destination is under no enabled location.
2. `--imports` on `verify-card`; `origin` and `culled` in the schema and the JSONL
   output. Tests: an imported file missing on its import location is culled whatever
   its other verdicts; an imported file still matched there must be matched everywhere;
   a file with no record is never culled; a record with the same name but a different
   data size doesn't match; a record whose location is disabled doesn't make the file
   culled.
3. `archive-source` treats culled files as cleared.
4. Verify screen: "Show culled", the culled count per import location, the "Not
   imported by Jetlag" marker, and the card-level "Safe to wipe" verdict naming the
   locations it was checked against.
