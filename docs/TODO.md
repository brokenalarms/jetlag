## `scripts/`

- (2026-02-20) **`tag-media.py` still makes a separate exiftool read for Make/Model** — `get_existing_exif_camera()` runs its own exiftool subprocess independent of any other data read for the file. For files where both EXIF and Finder tags need checking, this means 2 reads (tag list + exif) before deciding on writes. Low priority since these are already small reads, but could be merged if tag-media is ever extended to read more EXIF fields.

## `macos/`

## `scripts/` + `macos/`

## `web/`

- (2026-02-26) **Interactive before/after timeline slider** — Replace the static side-by-side cards in the Problem section with a draggable slider. Clips animate between broken and corrected positions as the user drags. Reuse existing `timeline.js` scale/positioning math. The before state is the default; dragging right reveals the corrected positions with smooth CSS transitions.
