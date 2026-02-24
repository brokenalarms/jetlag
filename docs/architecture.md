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

## Testing

Tests live in `scripts/tests/`.

- **Regression tests** — assert actual file state before and after, not just exit codes or stdout. Structured as "record before → run script → compare after" with human-readable expected vs actual diffs.
- **Performance tests** — snapshot harness. Runs media-pipeline end-to-end (3 files, fix-timestamp + organize), measures median wall-clock time over 3 runs, compares to a saved baseline. Threshold: 5% slower than baseline = regression. Delete the baseline file to re-record after intentional perf improvements.

Testing rules:
- Testing `returncode == 0` is not testing behavior — it only confirms the script didn't crash.
- Tests should not be updated without explicit confirmation unless following TDD (break test first, confirm expected failure, then update).
