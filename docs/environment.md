# Environments

Work happens in one of two places. Check which one you are in (`uname`) before running build or test commands; when a command behaves differently between them, record it here.

## macOS dev machine

The full toolchain: Xcode, Homebrew, `bd`.

- `make test` runs the script, web and design tests, then the Swift tests (`test-macos` is added only when `uname` is `Darwin`). The web tests need Node and npm. `make lint` runs ruff and pyrefly; `make check` runs lint and then test.
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
  - `media_pipeline/test_pipeline_cli.py::TestSummaryOutput::test_summary_shows_failed_files`
  - `media_pipeline/test_pipeline_organize.py::TestPipelineOutcomeLines::test_apply_mentions_working_dir_only_when_preserved_for_inspection`
  - `media_pipeline/test_pipeline_archive.py::TestArchiveSourceIntegration::test_archive_skipped_when_a_file_failed`

  To run them for real, run them as an unprivileged user on a world-writable copy of `scripts/` and `pyproject.toml` (outside any root-only directory), with the venv's Python:

  ```bash
  R=$(mktemp -d /tmp/jetlag-unpriv.XXXX) && cp -r scripts pyproject.toml "$R" && chmod -R a+rwX "$R"
  cd "$R" && runuser -u nobody -- env HOME=/tmp PATH=$R/scripts/tools:$PATH \
    scripts/.venv/bin/python -m pytest -p no:cacheprovider scripts/tests/media_pipeline \
    -k "test_summary_shows_failed_files or test_apply_mentions_working_dir_only_when_preserved_for_inspection or test_archive_skipped_when_a_file_failed"
  ```
- **ffmpeg:** the tests generate their media with `ffmpeg`. If a container lacks it, `apt-get install -y ffmpeg` (as CI does).
- **macOS-only script tests** (Finder tags, birth time) carry `skipif` markers and are skipped on Linux.
- **No Swift or Xcode:** `macos/` cannot be built or tested. For any change under `macos/` (or a `scripts/` change the app depends on), put a reviewer test plan in the PR: a checklist of steps to run in the live app and what each should show.
- **Web:** Node and npm are available, so `web/` builds (`cd web && npm install && npm run build`) and Playwright with Chromium is preinstalled, so `npm run screenshot --prefix web` works.
- **No `bd`:** work from `docs/specs/` and the user's instruction, and list newly found tasks in the PR description.

## CI

`.github/workflows/ci.yml` runs on pull requests on Ubuntu, not as root: the `test` job installs `ffmpeg` and `exiftool` with apt, then runs `make test-scripts` and `make lint`; the `web-design` job runs `make test-web` and `make test-design`. It does not build or test the macOS app.
