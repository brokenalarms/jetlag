# Architecture

## Layout

```
/                         ← repo root
├── scripts/              ← Python/shell scripts (work standalone, no knowledge of app)
│   ├── *.py / *.sh
│   ├── lib/              ← shared Python utilities
│   ├── media-profiles.yaml  ← shared config (used by both scripts and app)
│   └── tests/            ← script test suite (belongs with the scripts)
├── macos/                ← macOS SwiftUI app (sibling to scripts/, not nested inside)
│   ├── Sources/          ← Swift source files
│   │   └── Tools/jetlag-metadata/  ← Swift CLI for metadata operations
│   └── project.yml       ← XcodeGen project spec
├── web/                  ← Vite + Tailwind marketing site
│   └── src/sections/     ← each section is a standalone render function
├── design/               ← shared design tokens, app icon generation, screenshots
└── docs/                 ← documentation
```

`scripts/`, `macos/`, and `web/` are independent components. `scripts/` and `macos/` share `media-profiles.yaml`. `web/` and `macos/` share color tokens via `design/tokens.json`. The scripts have no knowledge of the app or website.

At build time, the `Bundle scripts` build phase copies `scripts/` into `Contents/Resources/scripts/` inside the app bundle.

---

## System overview

Three components that share config:

1. **Python scripts** (`scripts/`) — CLI tools for timestamp fixing, tagging, organizing, gyroflow generation. Run standalone or via shell wrappers.
2. **Jetlag macOS app** (`macos/`) — SwiftUI wrapper that reads the same `media-profiles.yaml`, edits profiles, and launches the scripts.
3. **Marketing site** (`web/`) — static site sharing the design token palette with the macOS app.

---

## Profile system (`media-profiles.yaml`)

Profiles are a YAML mapping where the **dict key is the profile name** — there is no `name` field inside a profile block. Example:

```yaml
profiles:
  gopro:
    file_extensions: [.mp4]
    tags: [gopro, action]
    exif:
      make: GoPro
      model: HERO12 Black
```

This dict-key-as-name constraint is shared between the Swift model and the Python scripts. Neither side should add a `name` field inside the profile — the key is the name.

---

## User-facing strings (`Strings.swift`)

All user-facing text in the macOS app is centralized in `macos/Sources/Strings.swift` for i18n readiness. The file uses Apple's `String(localized:defaultValue:)` API, which integrates with String Catalogs (`.xcstrings`) when translations are added later.

**Structure** — strings are organized by feature area as nested enums:

| Enum | Scope |
|---|---|
| `Strings.Common` | Shared buttons/actions: Cancel, Delete, Browse |
| `Strings.Nav` | Sidebar tab labels |
| `Strings.Pipeline` | Pipeline step labels and help text |
| `Strings.Workflow` | Workflow view: labels, placeholders, toggles, warnings, help text |
| `Strings.Profiles` | Profile editor: labels, placeholders, dialog text, help text |
| `Strings.Settings` | Settings view: sections, status, buttons |
| `Strings.Upgrade` | Upgrade dialog: titles, messages |
| `Strings.DiffTable` | Table column headers and status badges |
| `Strings.LogOutput` | Log output panel: title, buttons |
| `Strings.Errors` | Error messages from ProfileService, LicenseStore, ScriptRunner |

**Naming conventions:**
- Localization keys follow `section.element.type` format (e.g. `workflow.sourceDir.placeholder`)
- Static lets for fixed strings, static functions for interpolated strings (e.g. `Strings.DiffTable.fileCount(42)`)
- Labels: `fooLabel`, help text: `fooHelp`, placeholders: `fooPlaceholder`, buttons: `fooButton`

**Enum display names** — `PipelineStep` and `SidebarTab` expose a `.label` computed property that delegates to `Strings.Pipeline.*` / `Strings.Nav.*`. Views use `.label` for display instead of `.rawValue`.

**Rules:**
- All new user-facing strings must go in `Strings.swift` — no hardcoded strings in views or services
- Strings used in multiple views belong in `Strings.Common`
- Dynamic data (profile names, file paths, timezone identifiers) stays inline — only static text is centralized

---

## Metadata service

All EXIF/metadata operations go through `MetadataService` (`scripts/lib/metadata.py`),
which provides a unified `read_tags`/`write_tags` API. It delegates to one of two backends:

1. **`jetlag-metadata`** (preferred) — a Swift CLI tool (`macos/Sources/Tools/jetlag-metadata/`)
   that uses native Apple frameworks. Photos use ImageIO (`CGImageSource`/`CGImageDestination`)
   for EXIF read/write. Videos use binary QuickTime atom parsing for mvhd/mdhd timestamps and
   mdta keys (creationdate, make, model). Runs as a persistent process for low per-operation
   latency.
2. **ExifTool directly** (fallback) — used when `jetlag-metadata` isn't available
   (e.g. Linux CI without Swift). Uses ExifTool's native `-stay_open` protocol.

Backend selection is automatic: `MetadataService` looks for the `jetlag-metadata` binary
in `scripts/tools/` first, then `$PATH`, falling back to ExifTool if neither is found.

All scripts import the singleton: `from lib.metadata import metadata_service as exiftool`.
The `as exiftool` alias preserves call-site compatibility with the original ExifTool wrapper.

---

## Testing

Tests live in `scripts/tests/`.

- **Regression tests** — assert actual file state before and after, not just exit codes or stdout. Structured as "record before → run script → compare after" with human-readable expected vs actual diffs.
- **Performance tests** — snapshot harness. Runs media-pipeline end-to-end (3 files, fix-timestamp + organize), measures median wall-clock time over 3 runs, compares to a saved baseline. Threshold: 5% slower than baseline = regression. Delete the baseline file to re-record after intentional perf improvements.

Testing rules:
- Testing `returncode == 0` is not testing behavior — it only confirms the script didn't crash.
- Tests should not be updated without explicit confirmation unless following TDD (break test first, confirm expected failure, then update).
