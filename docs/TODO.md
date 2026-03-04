Note: larger todos may also be defined as specs in @docs/specs. These may be worked on, furthe broken down and updated if necessary, and moved to docs/specs/completed when done. Task completion and maintenance rules including this one are all present in AGENTS.md.

## `scripts/`

- (2026-02-20) **`tag-media.py` still makes a separate exiftool read for Make/Model** — `get_existing_exif_camera()` runs its own exiftool subprocess independent of any other data read for the file. For files where both EXIF and Finder tags need checking, this means 2 reads (tag list + exif) before deciding on writes. Low priority since these are already small reads, but could be merged if tag-media is ever extended to read more EXIF fields.

## `macos/`

## `scripts/` + `macos/`

## `web/`
