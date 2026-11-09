# Maintainability audit

## Goal

Make the codebase easier to compose, test, extend and maintain without changing
behaviour. Each item below is sized (S/M/L) and meant to land as its own PR. The order
is the suggested order of work. Line numbers are as of commit `b48e3eb`.

## What to keep

These patterns work and later refactors should build on them, not replace them:

- `scripts/lib/exiftool.py` is the only exiftool client. It keeps one `-stay_open`
  process per run and is the single metadata seam.
- `scripts/pipeline-schema.yaml` defines the JSONL contract. It is checked from both
  sides: by `scripts/tests/pipeline_schema.py` and by
  `macos/Tests/PipelineSchemaContractTests.swift`. Extend this pattern; don't add a
  parallel one.
- The scripts' core functions return dataclasses (`TimestampFixResult`, `TagResult`,
  `OrganizeResult`, …). The pipeline calls these functions in-process, and every file
  gets exactly one exiftool write (`extra_write_fields`).
- On the app side, `RowOutcome` uses exhaustive switches over tokens. `ProfilesLocation`
  is injected into `AppState`. `startRun` has closure seams (`RunStartTests`).
  `PythonRuntimeCheck` takes closures. `ScriptRunner`/`ScriptProcess` manage process
  groups.
- Web sections are small, standalone render functions. `timeline.js` already separates
  its pure logic from the DOM.

---

## 1. Correctness found during the audit (do first)

### 1a. Saving profiles from the app drops keys the app doesn't model (S–M)

`MediaProfile` (`macos/Sources/Models/MediaProfile.swift:90`) has no `folder_template`,
but `scripts/media-pipeline.py:605` reads it. `AppState.writeProfiles`
(`AppState.swift:931`) re-encodes the whole file, so the first save from the app
deletes `folder_template` and any other key the app doesn't model.

There is a second problem. `loadProfiles` stores the `.normalized()` config, which
copies the global gyroflow preset into each profile. That copy is what gets written, so
after one save, changing the global preset no longer reaches those profiles.

- Write from the raw config. Apply normalization only when reading.
- Keep unknown keys, either by passing them through or by editing the Yams `Node`
  tree.
- Add a round-trip test: a fixture with `folder_template` and an unknown key survives a
  load → edit → save.

### 1b. Renaming a profile can overwrite another one (S)

`ProfilesView.saveCurrentProfile` (`ProfilesView.swift:347`) writes the edited profile
under the new name without checking whether that name is already taken, and `canSave`
(`:8`) has no uniqueness check. `ProfileTests.testRenameProfile` rebuilds the
dictionary edit by hand instead of calling app code, so it can't catch this. Fix this as
part of item 4.

---

## 2. Docs and tooling that give agents conflicting instructions (S each)

- **Task tracking.** `AGENTS.md` says to work from `docs/TODO.md`. `docs/TODO.md` says
  tasks live in bd (beads), and `bd` is not installed in Linux sessions. Choose one
  system. If it's beads, say what to do when `bd` isn't available.
- **Missing file.** `AGENTS.md` points to `docs/environment.md`, which doesn't exist.
  Create it.
- **Spec folders.** `AGENTS.md` refers to both `docs/specs/completed` and
  `docs/specs/implemented`; only `completed/` exists. `docs/committing.md` refers to a
  `todos/` folder that doesn't exist, and tells you to mark sub-steps in specs, which
  `AGENTS.md` forbids.
- **Duplicated testing rules.** The same "Testing rules" appear in `architecture.md`
  and `testing.md`. Keep them in `testing.md` and link to it from `architecture.md`.
- **Stale app docs.** Two "Known gotchas" in `macos/AGENTS.md` are out of date:
  - The `@@` filtering note is stale. The pipeline now emits JSONL, and
    `LogLine.isMachineReadable` filters on a leading `{`.
  - The `ScriptRunner` race note describes a race that is already fixed.
- **Old files.** `scripts/tests/TEST_SUMMARY.md` is an old generated summary that
  overlaps `tests/README.md`. The root `package-lock.json` is an empty stub with no
  `package.json`.
- **"No view models" rule.** `macos/AGENTS.md` forbids view models. Reword it to say
  that plain services and reducers owned by `AppState` are allowed, so items 4–6 aren't
  undone by later sessions.

## 3. CI, linting, one test entry point (S–M)

- CI runs only `pytest scripts/tests/ -x`. It skips `scripts/tests/requirements.txt`
  (xdist), so it runs serially. Call `make test-scripts` instead.
- Add CI jobs for:
  - `pyrefly check` (already configured in `pyproject.toml`; nothing runs it);
  - the web build (`npm ci && npm run build`);
  - a token-drift check (see item 10).
- Add `make lint`: pyrefly, plus ruff with a small rule set (E722 bare except,
  F401/F841 unused names). Four bare `except:` exist in `fix-media-timestamp.py` (107,
  134, 150, 1032).
- Delete `scripts/run-tests.py`, or make it call `make test-scripts`. Add `test-web` to
  `make test` once item 11 exists.
- Python packaging:
  - Set `pythonpath = ["scripts"]` in the pytest config so tests can drop their
    `sys.path` hacks.
  - Merge the three requirements files.
  - Stop `conftest.py` from pip-installing at runtime.
  - Keep the scripts runnable without being installed, since the app bundles
    `scripts/` as-is.

---

## 4. scripts/: identify timestamp sources by token, not by display string (M)

`lib/timestamp_source.get_best_timestamp` returns English labels such as
`"DateTimeOriginal with timezone"` and `"file birthtime"`. `fix-media-timestamp.py` then
branches on substrings of those labels (`:634`, `:638`, `:694`, `:924`).
`_source_to_machine_token` (`:875`) maps the labels back to tokens by trying substrings
in order. As a result, rewording a label silently changes both the branching and the
machine token, and adding a source touches about six places.

- Add a `TimestampSource` enum carrying `display`, `token` and `is_utc`, and return it
  from `get_best_timestamp`.
- Express the ranking as an ordered list of small rule functions
  (`(exif, filename, tz) -> Optional[Candidate]`), so that adding a source means one
  rule plus one enum member.
- This removes the two identical UTC branches in `get_all_timestamp_data` (`:535` and
  `:549`). Both re-parse the offset inline instead of calling `_timezone_from_offset`.

## 5. scripts/: move script logic into importable `lib/` modules (M)

`media-pipeline.py:40` loads six sibling scripts with
`importlib.import_module("tag-media")` and similar calls. Nine test files load scripts
with `spec_from_file_location`, so the module a test monkeypatches is not the module
the pipeline uses. Shared helpers are stuck in CLI files:

- `get_timezone_for_country` in `fix-media-timestamp.py`;
- `camera_mismatch` in `tag-media.py`;
- `is_protected` in `ingest-media.py`.

- Move each script's logic to a module with an ordinary name: `lib/fix_timestamp.py`,
  `lib/tagging.py`, `lib/organize.py`, `lib/ingest.py`, `lib/gyroflow.py`,
  `lib/archive.py`, `lib/timezones.py`.
- Keep each hyphenated script as a thin argparse + `emit_result` shim, so the CLI names
  the app calls don't change.
- Remove the pass-through `run_*` wrappers in `media-pipeline.py` (`:233-391`).
- Tests use plain imports.

## 6. scripts/: break up the pipeline's god functions (L)

`process_file` (`media-pipeline.py:394-699`) takes 17 parameters and handles every stage
inline:

- It repeats the same five-line failure exit five times.
- It routes on `"tag" in tasks` string checks.
- It keeps run state in the module globals `_staged_paths` and `_working_dir`.

`main` (about 350 lines) contains three hand-written consent prompts, timezone
validation and the timezone pre-flight.

- Add `RunOptions`, a frozen dataclass built from args.
- Add a `FileContext` that holds the active file, its companions and the staged
  paths.
- Model each step as a `Stage` with `name`, `enabled(opts, profile)` and
  `run(ctx) -> StageOutcome`. One loop handles `stage_complete` and failure exits.
  Adding a step then means one class plus one schema entry.
- Pull out `require_consent(flag, prompt, refusal_lines)` and a pure
  `preflight_timezones(files, spec)`.
- Put the staging state on a `WorkingDir` object that the signal handler closes
  over.

In the same way, split `fix_media_timestamps` (`fix-media-timestamp.py:893-1127`) into:

- a pure `plan_correction(current, opts) -> CorrectionPlan`;
- `describe(plan)`, which produces the stderr text;
- `apply(plan)`, which makes one write.

Most of the 1,491-line unit test file can then test plans without exiftool.

## 7. scripts/: metadata seam and shared CLI helpers (S each)

- **Exif cache.** `fix-media-timestamp.py` imports the private `_exif_cache` and changes
  it directly, and tests clear it by hand.
  - Have `lib/exiftool` invalidate the cache on write.
  - Add an autouse fixture that clears it.
  - Let `ExifTool(binary=...)` be constructed directly so a fake can be passed in
    without setting an environment variable before import.
- **Profile YAML loading** is duplicated in `media-pipeline.py:150` and
  `generate-gyroflow.py:123`. Add `lib/profiles.load_profile(name)`.
- **Default folder template** is defined in both the pipeline and `organize-by-date.py`.
  Keep one default, in `expand_path_template`.
- **Timezone arguments differ between scripts.**
  - The pipeline accepts only `+HHMM`, while fix-media-timestamp also accepts
    `+HH:MM`.
  - The pipeline calls the option `--location`, while fix-media-timestamp calls it
    `--country`.
  - Add `lib/cli.py` with `add_timezone_args` and `resolve_timezone`.
- **Small inconsistencies.**
  - The pipeline strips whitespace around tags, but `tag-media.py` doesn't.
  - Some functions take `dry_run=` and others take `apply=`. Settle on `apply`.
  - Five scripts each have their own SIGINT handler, and only the pipeline handles
    SIGTERM.
- **Dead code.**
  - `write_keys_creationdate` and `write_quicktime_createdate` are called only from
    tests, and they contradict the one-write-per-file rule. `read_provenance_record` is
    also called only from tests; keep it if verify-card needs it.
  - Two docstrings are stale: `lib/results.py` (says it will be deleted at "step 3") and
    `fix-media-timestamp.py:84` (refers to "bash lines").
  - Delete the batch `.sh` wrappers nothing calls, or make them thin loops.

## 8. macos/: an injectable script launcher, and the run lifecycle in AppState (M)

`ScriptRunner.run` is called statically from `WorkflowView`, `AppState`, `CameraProbe`
and `SourceScan`. `runWorkflow`/`startPipeline` (`WorkflowView.swift:529-576`) handle
the media count, assent gating, process launch, the drain task and `finishRun` inside a
view.

- Add a `ScriptLaunching` protocol, with a live implementation that captures the scripts
  directory and the profiles path, and inject it into `AppState.init`.
- Move `startPipeline` into `AppState`.
- Tests can then feed a scripted stream of JSONL lines and check rows, the summary and
  alerts end to end.
- `LicenseStore.shared` writes `UserDefaults.standard` directly. Give it
  `init(defaults:)` so the free-tier limit can be tested.

## 9. macos/: split AppState.swift and pull out reducers (M, mostly mechanical)

`AppState.swift` (1,184 lines) contains five separate things: `SidebarTab`/`PipelineStep`,
`LogLine`, the `PipelineEvent` decoder, `WorkflowSession` and `AppState`.

- Give each its own file.
- Pull the event reducer (`parseMachineReadableLine`, `:963-1070`) out into a value
  type, `RunTranscript.apply(_ event:)`. It owns the rows, the live row and the summary,
  and returns conflict events for `AppState` to handle. It can be tested without
  `AppState()`, which unwraps `Bundle.main.resourcePath!`.
- Move the profile CRUD out of `ProfilesView` (`:338-382`) into `ProfilesConfig`
  methods, with a name-collision error (fixes 1b). This leaves one unique-name generator
  instead of two (`"name 2"` vs `"name copy N"`).
- Build `WorkflowSession` through one `AppState.selectProfile(_:)` instead of four call
  sites. `WorkflowView.onAppear` currently rebuilds it on every visit to the tab and
  loses the chosen timezone.
- Move view helpers into models:
  - `timezoneConflictMessage`, `runSummaryMessage` and `fixTimestampPreview` from
    `WorkflowView`;
  - `destinationPreview`, which also ignores `folder_template`.
- Replace bare string tokens (`"mixed_timezones"`, `"changed"`, `"failed"`) with
  enums.
- Remove dead code: the unused `SandboxView.swift`, 11 unused `Strings` entries, and the
  `gyroflowResult` fields that are decoded and never used.

## 10. One source of truth for pipeline steps and CLI flags (M, scripts/ + macos/)

Adding a step currently touches about eight places:

- the `PipelineStep` switches;
- the `taskNames` map in `buildPipelineArgs`;
- `computeAvailableSteps` and `isStepReady`;
- `stepOptionsContent`;
- `DiffTableRow.stageOrder`/`stageLabelMap` (hardcoded English, missing
  `archive-source`);
- the Python `choices=[...]` (`media-pipeline.py:744`).

Changes:

- Add a `cli:` section to `pipeline-schema.yaml` listing task tokens and flag names.
- Give `PipelineStep` a `taskToken` and a `stageToken`, and derive the stage order and
  labels from `allCases`.
- Check both sides against the schema: extend `PipelineSchemaContractTests`, and add a
  Python test that checks the argparse definition.

## 11. web/ and design/ (S–M)

- **Tokens.** `web/src/style.css` redefines the token colours as CSS variables, and
  repeats them in about 49 `rgba(...)` literals. `tailwind.config.js` hardcodes
  `neutral.*` shades. `design/generate-app-icon.py` has its own colour block.
  - Generate the CSS variables from `design/tokens.json` as `r g b` triplets.
  - Have the icon script read `tokens.json`.
  - Give `design/generate-colorsets.py` (which maps 5 of the 10 tokens) a `--check`
    mode, add a `make tokens` target, and run the check in CI.
- **Tests.**
  - Add Vitest, with unit tests for the pure functions in `timeline.js`.
  - Add a smoke test that renders every section, checks section ids are unique, and
    checks every `#anchor` has a target.
- **Content constants.**
  - The price, the buy URL and the 50-file free limit are repeated across several
    sections. The limit is also hardcoded separately in
    `macos/Sources/Services/LicenseStore.swift:48`.
  - Put them in `web/src/content.js`.
  - Optionally share the limit with the app through `design/product.json`, the same way
    the tokens are shared.
- **Repeated markup.** The section header is copied into six sections. Add
  `components/section-header.js`. Nav links are written twice; use one `NAV_LINKS`
  array.
- **Wrong dependency type.** Playwright is in `dependencies`, so every Netlify deploy
  installs it. Move it to `devDependencies`.
- **`screenshot.js`.**
  - Its comments name the wrong output directory.
  - It uses `nth-of-type` selectors because hero and problem have no ids.
  - It leaves orphaned PNGs in `design/screenshots/`.

## 12. Move routing tests in-process (L, gradual, after items 5–6)

`scripts/tests/test_media_pipeline.py` (3,129 lines) calls `run_pipeline` 90 times. Each
call starts `bash media-pipeline.sh`, which means a fresh Python process and a fresh
exiftool every time. Many of these tests check routing only: group templates,
timezone validation, summaries.

- Once stages and pre-flight are pure, test them in-process with a fake metadata
  client.
- Keep about 15 end-to-end subprocess tests for the CLI and the JSONL contract.
- Split the file by area: discovery, timezones, organize, companions, cancel.
