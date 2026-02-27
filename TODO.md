## `scripts/`

- (2026-02-20) **`tag-media.py` still makes a separate exiftool read for Make/Model** — `get_existing_exif_camera()` runs its own exiftool subprocess independent of any other data read for the file. For files where both EXIF and Finder tags need checking, this means 2 reads (tag list + exif) before deciding on writes. Low priority since these are already small reads, but could be merged if tag-media is ever extended to read more EXIF fields.

## `macos/`

- (2026-02-24) **Timeline visualization** — Horizontal timeline view showing files as colored blocks per camera, positioned by timestamp. Two rows per camera: "before" (scattered, gaps from timezone errors) and "after" (correctly interleaved). Builds on diff table data. Use the neon color palette already defined in Assets (NeonCyan, NeonPink, NeonYellow, NeonPurple) to distinguish cameras.

- (2026-02-24) **Pipeline steps visual redesign** — Render pipeline steps as a connected horizontal chain with a line behind them. Always-on steps (ingest, output) shown in green, non-toggleable. Optional steps (tag, fix-timestamp, gyroflow, archive-source) are toggleable. Enabling a task in the chain causes its configuration options to appear as grouped rows below (e.g. enabling archive-source reveals source action picker: leave/archive/delete, with yellow accent).

- (2026-02-24) **Timezone map in picker** — MapKit and CoreLocation are already linked in `project.yml` but unused. Replace or augment `TimezoneMapView` with an actual map showing timezone boundaries. When footage timezone differs from current system timezone, show both on the map with a visual arc.


## `scripts/` + `macos/`

- (2026-02-27) **Time correction pipeline step** — Refactor: extract tiered timestamp reader into `lib/timestamp_source.py` with generic filename date patterns (prefix-agnostic). Features: `--time-offset` and `--infer-from-filename` on `fix-media-timestamp.py`, new `report-file-dates.py` (pre-flight scanner). Pipeline: inline rename after fix-timestamp using `build_filename()` from shared lib. App: timestamp source selector, offset field (with reference-time calculator), filename update toggle within Fix Timestamps step. Spec: `todos/time-correction-pipeline-step.md`

- (2026-02-27) **Per-profile `filename_timestamp_patterns`** — Allow profiles in `media-profiles.yaml` to define custom filename date patterns for cameras using non-standard formats. Generic detection covers all known cameras today; this is future-proofing for when a real camera needs it. Low priority.

## `web/`

- (2026-02-26) **Interactive before/after timeline slider** — Replace the static side-by-side cards in the Problem section with a draggable slider. Clips animate between broken and corrected positions as the user drags. Reuse existing `timeline.js` scale/positioning math. The before state is the default; dragging right reveals the corrected positions with smooth CSS transitions.
