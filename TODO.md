## `scripts/`

- (2026-02-20) **`tag-media.py` still makes a separate exiftool read for Make/Model** — `get_existing_exif_camera()` runs its own exiftool subprocess independent of any other data read for the file. For files where both EXIF and Finder tags need checking, this means 2 reads (tag list + exif) before deciding on writes. Low priority since these are already small reads, but could be merged if tag-media is ever extended to read more EXIF fields.

## `macos/`

- (2026-02-24) **Timeline visualization** — Horizontal timeline view showing files as colored blocks per camera, positioned by timestamp. Two rows per camera: "before" (scattered, gaps from timezone errors) and "after" (correctly interleaved). Builds on diff table data. Use the neon color palette already defined in Assets (NeonCyan, NeonPink, NeonYellow, NeonPurple) to distinguish cameras.

- (2026-02-24) **Pipeline steps visual redesign** — Render pipeline steps as a connected horizontal chain with a line behind them. Always-on steps (ingest, output) shown in green, non-toggleable. Optional steps (tag, fix-timestamp, gyroflow, archive-source) are toggleable. Enabling a task in the chain causes its configuration options to appear as grouped rows below (e.g. enabling archive-source reveals source action picker: leave/archive/delete, with yellow accent).

- (2026-02-24) **Timezone map in picker** — MapKit and CoreLocation are already linked in `project.yml` but unused. Replace or augment `TimezoneMapView` with an actual map showing timezone boundaries. When footage timezone differs from current system timezone, show both on the map with a visual arc.

## `scripts/` + `macos/`

- (2026-02-24) **Per-file progress cards** — During apply mode, replace scrolling logs with a card-based UI. Each file gets a card showing pipeline stages as checkmarks: Tagged → Timestamp Fixed → Organized → Gyroflow. Failed stages show red. Cards expand to show details.
   - `scripts/`: `media-pipeline.py` needs to emit `@@stage_complete=<stage>` after each step
   - `macos/`: card-based progress view consuming `@@stage_complete` events

## `web/`

(no open tasks)
