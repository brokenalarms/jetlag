Note: larger todos may also be defined as specs in @docs/specs. These may be worked on, furthe broken down and updated if necessary, and moved to docs/specs/completed when done. Task completion and maintenance rules including this one are all present in AGENTS.md.

## `scripts/`

- (2026-02-20) **`tag-media.py` still makes a separate exiftool read for Make/Model** — `get_existing_exif_camera()` runs its own exiftool subprocess independent of any other data read for the file. For files where both EXIF and Finder tags need checking, this means 2 reads (tag list + exif) before deciding on writes. Low priority since these are already small reads, but could be merged if tag-media is ever extended to read more EXIF fields.

## `macos/`

- (2026-08-11) **The app bundle ships pytest and pyrefly** — `requirements.txt` mixes runtime deps (PyYAML, humanize) with dev-only tooling, and the `Bundle scripts` phase vendors all of it into `Contents/Resources/scripts/site-packages`, ~35MB of which is test tooling a user never runs. Split into `requirements.txt` and `requirements-dev.txt`, vendor only the former.
- (2026-08-11) **bd is unusable — `pending schema migrations alter pre-existing dirty tables: comments, events, issues`** — every `bd create` and `bd migrate` fails with this, so issues found during a session have nowhere to go but this file.

## `scripts/` + `macos/`

- (2026-08-11) **The app cannot tell a missing interpreter from a Command Line Tools stub** — on a Mac without Xcode or CLT, `/usr/bin/python3` triggers the developer-tools install dialog instead of running, so a user hits an opaque failure. See the open risk in @docs/specs/python-runtime.md; the app should detect this and say what to install.

## `web/`
