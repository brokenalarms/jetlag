# Environments

Work happens in one of two places. Check which one you are in (`uname`) before running build or test commands; when a command behaves differently between them, record it here.

## macOS dev machine

The full toolchain: Xcode, Homebrew, `bd`.

- `make test` runs the script tests and then the Swift tests (`test-macos` is added only when `uname` is `Darwin`).
- `make test-macos`, `make build`, `make` and `make dmg` all run `xcodegen generate` first, so they need `brew install xcodegen`.
- `make test-scripts` bootstraps `scripts/.venv` on first run and re-installs whenever a requirements file changes.
- `tag` and `exiftool` are vendored in `scripts/tools/`; `SetFile` comes from the Xcode command-line tools (`xcode-select --install`).
- Tasks: `bd ready`, `bd prime`.

## Linux cloud container

Scripts and the web site only. Sessions usually run as root.

- **Script tests:** `exiftool` is vendored in `scripts/tools/` but is not on `PATH`, and several tests call it directly. Run:

  ```bash
  PATH=$PWD/scripts/tools:$PATH make test-scripts
  ```

  `make test-scripts` stops at the first failure (`-x`). To see every failure, run pytest directly after the venv exists:

  ```bash
  PATH=$PWD/scripts/tools:$PATH scripts/.venv/bin/pytest scripts/tests -q -n auto
  ```

- **Known failures as root:** root ignores `chmod 000`, so the tests that make a file unreadable to force a failure see it succeed instead. These three fail in a root container and pass on macOS; anything else failing is a real regression:
  - `test_media_pipeline.py::TestSummaryOutput::test_summary_shows_failed_files`
  - `test_media_pipeline.py::TestPipelineOutcomeLines::test_apply_mentions_working_dir_only_when_preserved_for_inspection`
  - `test_media_pipeline.py::TestArchiveSourceIntegration::test_archive_skipped_when_a_file_failed`
- **macOS-only script tests** (Finder tags, birth time) carry `skipif` markers and are skipped on Linux.
- **No Swift or Xcode:** `macos/` cannot be built or tested. For any change under `macos/` (or a `scripts/` change the app depends on), put a reviewer test plan in the PR: a checklist of steps to run in the live app and what each should show.
- **Web:** Node and npm are available, so `web/` builds (`cd web && npm install && npm run build`) and Playwright with Chromium is preinstalled, so `npm run screenshot --prefix web` works.
- **No `bd`:** work from `docs/specs/` and the user's instruction, and list newly found tasks in the PR description.

## CI

`.github/workflows/ci.yml` runs on pull requests on Ubuntu, not as root: it installs `ffmpeg` and `exiftool` with apt and runs `pytest scripts/tests/ -x`. It does not run the Swift tests.
