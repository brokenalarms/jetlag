Note: larger todos may also be defined as specs in @docs/specs. These may be worked on, furthe broken down and updated if necessary, and moved to docs/specs/completed when done. Task completion and maintenance rules including this one are all present in AGENTS.md.

## `scripts/`

- (2026-02-20) **`tag-media.py` still makes a separate exiftool read for Make/Model** — `get_existing_exif_camera()` runs its own exiftool subprocess independent of any other data read for the file. For files where both EXIF and Finder tags need checking, this means 2 reads (tag list + exif) before deciding on writes. Low priority since these are already small reads, but could be merged if tag-media is ever extended to read more EXIF fields.
- (2026-08-12) **Surface the inferred camera zone in dry-run data** — `filename − QuickTime date`, when a legal zone offset, IS the camera's zone setting at shoot time; it's computed in `_quicktime_is_instant()` and discarded. Emit as `@@camera_zone_offset` whenever filename and a usable QuickTime date coexist, so the diff table can show camera zone vs embedded label vs declared zone (answers "was the camera still on Taipei time?" from the dry run itself).
- (2026-08-12) **Read `OffsetTimeOriginal` to complete a bare `DateTimeOriginal`** — it is always and only the zone of DTO's digits (EXIF 2.31; binary EXIF DTO has no room for an inline zone). Generic supplement rule, matters for photo profiles. Also verify what exiftool does when writing a zoned DTO value to a still (auto-split into OffsetTimeOriginal, or dropped?). See docs/timestamp-fields.md.
- (2026-08-12) **Bare `Keys:CreationDate` (no zone, no Z) is silently ignored as a source** — decided it should rank as a naive source alongside bare DTO (rank 6), requiring a declared zone. See docs/timestamp-fields.md ranking table.
- (2026-08-12) **Timezone-mismatch block in `media-pipeline.py` becomes informational** — `media-pipeline.py:~707` still exits 1 on provided-vs-embedded mismatch even in dry-run; per the agreed flow (and time-correction-pipeline-step.md), dry-run always previews with conflicts as data and per-file `requires_force_timezone` gates the apply. App side: diff table highlights conflicted rows from `requires_force_timezone`, apply button prompts assent which re-runs with `--force-timezone`. `fix-media-timestamp.py` already emits the field.
- (2026-08-12) **Healing spec for previously mis-zoned files** — files stamped by earlier runs with a wrong declared zone have wrong UTC in headers but intact track atoms and corrected filenames. Spec a reconciliation report: per file, filename date vs track date vs header date vs implied offset, verdict column (consistent / already-fixed / damaged), rendered as a table for manual verification before any write. Taiwan first days additionally need `--offset` (camera clock itself was wrong, then fixed).

## `scripts/` + `macos/` (gyroflow)

- (2026-08-12) **Bundle gyroflow properly, as an install-time option** — the bare-binary bundling from #121 never worked (signature invalidated outside the app bundle; missing mdk/Qt frameworks) and the dead binary is now removed (PR #139). Agreed design: install-time checkbox that downloads the full `Gyroflow.app` into `scripts/tools/` (gitignored) via `download-gyroflow.sh`; detect existing installs first (`/Applications/Gyroflow.app`, `which gyroflow`) and say "found — will use existing" instead of downloading; `resolve_gyroflow_binary()` resolves existing install → bundled app; the app gates all gyroflow UI on that single presence flag.

## `macos/`

- (2026-08-11) **The app bundle ships pytest and pyrefly** — `requirements.txt` mixes runtime deps (PyYAML, humanize) with dev-only tooling, and the `Bundle scripts` phase vendors all of it into `Contents/Resources/scripts/site-packages`, ~35MB of which is test tooling a user never runs. Split into `requirements.txt` and `requirements-dev.txt`, vendor only the former.
- (2026-08-11) **bd is unusable — `pending schema migrations alter pre-existing dirty tables: comments, events, issues`** — every `bd create` and `bd migrate` fails with this, so issues found during a session have nowhere to go but this file.

## `scripts/` + `macos/`

- (2026-08-11) **The app cannot tell a missing interpreter from a Command Line Tools stub** — on a Mac without Xcode or CLT, `/usr/bin/python3` triggers the developer-tools install dialog instead of running, so a user hits an opaque failure. See the open risk in @docs/specs/python-runtime.md; the app should detect this and say what to install.

## `web/`
