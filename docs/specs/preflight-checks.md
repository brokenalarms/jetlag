# Batch checks: one sequence, one output

Read `timestamp-handoff.md`'s principles first: the script is the source of truth, the
app composes arguments and renders tokens, and every token is enumerated in
`pipeline-schema.yaml` and pinned on both sides by contract tests.

## Problem

Every batch-level check was built on its own, and each one repeats the same idea in
its own shape:

| Check | Script | Event | Consent flag | App state |
|---|---|---|---|---|
| protected sources | `check_protected_sources` | `protected_sources {files}` | `--unlock-protected` | `protectedSourceFiles`, `showProtectedSources`, `unlockProtected`, one alert |
| camera mismatch | `check_source_camera` | `camera_mismatch {files, expected_*, found_*}` | `--allow-camera-mismatch` | `cameraMismatch`, `showCameraMismatch`, `allowCameraMismatch`, one alert |
| mixed zones | `check_timezones` | `timezone_conflict {conflict_type: mixed_timezones, file_timezones}` | `--allow-mixed-timezones` | `timezoneConflict*`, `showTimezoneConflict`, `allowMixedTimezones`, one alert |
| zoned tag differs from `--timezone` | `check_timezones` | `timezone_conflict {conflict_type: provided_mismatch, …}` | `--force-timezone` | shares the mixed-zone state and alert |
| unparseable filenames under `--infer-from-filename` | `check_filename_timestamps` | `filename_parse_error {unparseable_files}` | none, always refuses | none |
| destination holds a different file (after the batch) | organize | `organize_conflict {count, files}` | `--overwrite` | `organizeConflict*`, `showOverwriteConflict`, `overwriteDestination`, one alert |

Each check differs in when it refuses: mixed zones refuse a dry run too, the others
refuse only an apply. The app re-derives that per check (`AppState`: "only an apply
asks", except for mixed zones). Adding the one check this spec needs, the timestamp
step being off, would be a seventh copy of all of it.

## Design

### Script: one runner over a list of checks

`lib/media_pipeline/preflight.py` holds `CHECKS`, in the order the user meets them.
Each check is declared the same way:

- `token`: the name the event carries, enumerated in the schema.
- `applies(opts)`: whether the check runs at all.
- `find(files, opts)`: the finding or None. It is pure over the files' `FileReading`s
  (`lib/timestamps/sources.py`), so it reads nothing the pipeline does not already
  read once.
- `assent_flag`: the flag that lets the run go on, or None for a check that always
  refuses.
- `refuses`: `apply` or `always`.

A finding is data only: `files`, plus an optional `groups` map (label → files) for
checks that split the batch, such as mixed zones by zone or camera mismatch by the
camera found.

One runner, `run_checks(files, opts)`, goes through `CHECKS` and emits one event per
finding:

```
{"event": "batch_check", "check": "<token>", "files": [...], "groups": {...},
 "assent_flag": "--allow-…", "refused": true}
```

`refused` says whether this run stops on the finding: the check refuses this mode
and the flag was not given. The app reads it and never works it out itself. The
runner gathers every finding first and then stops once, so a run that hits several
checks asks about all of them in one go rather than one per re-run. `require_consent`
stays the single terminal prompt, with one prompt per refusing finding. Human lines
on stderr come from one formatter keyed by token.

`organize_conflict` happens after the batch, not before it, but it is the same shape
of thing: a finding, its files and an assent flag. It is emitted as a `batch_check`
with `check: destination_occupied`. Nothing in it refuses, because the run has
already finished; the flag applies to the re-run.

### Checks after this change

| Token | Refuses | Assent flag | Finding |
|---|---|---|---|
| `protected_sources` | apply | `--unlock-protected` | files with the user-immutable flag |
| `camera_mismatch` | apply | `--allow-camera-mismatch` | files whose Make/Model differ from the profile's; groups by camera found |
| `timestamps_unset` | apply | `--allow-unset-timestamps` | every file, when the Set Timestamps step is off. **New.** |
| `mixed_timezones` | always | `--allow-mixed-timezones` | groups by `FileReading.zone`; files with no zone evidence form their own `none` group, so a mix of zoned and unzoned files is mixed |
| `zone_relabel` | apply | `--force-timezone` | files whose zoned tag differs from `--timezone` (was `provided_mismatch`); groups by tag zone |
| `filename_unparseable` | always | none | under `--infer-from-filename`, files with no date in their name |
| `destination_occupied` | never (after the batch) | `--overwrite` | files left in place because a different file holds their destination |

The flag names stay the same, so command lines and scripts that use them keep
working. The old event names are deleted rather than kept alongside the new one: the
contract tests make sure both sides move together.

### App: one model, one alert

- `BatchCheck` is the decoded event. `pendingChecks: [BatchCheck]` holds the refused
  ones from the last run, and `grantedAssent: Set<String>` holds flags granted for
  this click. `buildPipelineArgs()` appends `grantedAssent`. `assentFlags` comes
  from the schema's `assent_flags`, not a hand-kept list.
- One alert presents `pendingChecks`. Its title, message and confirm button come
  from a table keyed by token in `Strings.swift`, and that is the only per-check
  code in the app. The message lists the groups the event carries.
- The per-check `show…`/`allow…`/files properties, their alerts and their
  `clearRunAssent()` lines are deleted.
- The run summary's camera-mismatch line becomes a line per finding the dry run
  reported.

### Set Timestamps

- The step is labelled **Set Timestamps** (results row: **Set TS**). It applies the
  hierarchy's time to every file whether or not anything was wrong, so "Fix" undersold
  it. The token stays `fix-timestamp`, and `fix-media-timestamp.sh` keeps its name.
- It stays switchable. With it off, a dry run shows the `timestamps_unset` warning and
  previews anyway. An apply stops on it until the user confirms, which sends
  `--allow-unset-timestamps`. This is how the Comedy night C0199 import would have
  been caught.
- With the step off, the app still passes `--timezone`, so the date folder is the
  date where the footage was shot (`FileReading.date_folder()`).

## Tests

- Script: one parametrised test over `CHECKS`. For each check, a batch that triggers
  it emits exactly one `batch_check` with the token, files and groups; a dry run and
  an apply each refuse or go on as the table says; with the assent flag the run goes
  on. The X6 batch and a zoned-plus-unzoned batch are `mixed_timezones`.
- Contract: the schema enumerates `check` tokens and `assent_flags`, and
  `PipelineSchemaContractTests` holds the Swift token table and `buildPipelineArgs()`
  to them. Add a token on one side only and a test fails.
- App: `AppStateTests` checks that a refused `batch_check` raises the one alert and
  that granting it re-runs with the flag; there is one test for the alert, not one
  per check.

## Order

One PR. The event, the schema and both sides of the contract change together, and
the macOS suite has to run locally before it merges.
