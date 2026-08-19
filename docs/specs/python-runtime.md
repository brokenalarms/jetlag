# Python runtime

## Constraint

The scripts run on the Python that ships with macOS. A user who installs the app
installs nothing else — no Homebrew, no pyenv, no `pip install`.

That sets the floor at **Python 3.9**, the version bundled with macOS 14–15
(`/usr/bin/python3` reports 3.9.6). The floor moves only when the oldest
supported macOS ships something newer.

## Resolving the interpreter

`lib/ensure-venv.sh`, sourced by every `*.sh` wrapper, resolves `JETLAG_PYTHON`
and the wrappers exec that rather than `python3`. Resolution order:

1. `$JETLAG_PYTHON`, if set and at or above the floor — for testing another interpreter
2. `/usr/bin/python3` — what a user has
3. the first `python3` on `PATH` at or above the floor

Pinning matters because `python3` means different things by launch context: a
terminal with Homebrew first finds 3.14, while an app launched from Xcode finds
Xcode's bundled 3.9 framework. Code that only ever ran from a terminal can fail
the first time it runs from the app.

## Dependencies

Requirements are pure-Python except PyYAML, which ships a C extension — wheels
built for one minor version fail to import on another, so whatever installs them
must be the same interpreter that runs them.

- **App bundle**: the `Bundle scripts` phase in `macos/project.yml` installs into
  `Contents/Resources/scripts/site-packages` with `/usr/bin/python3`. At runtime
  `ensure-venv.sh` finds that directory and puts it on `PYTHONPATH`.
- **Checkout**: `.venv/` is created on first run with the resolved interpreter,
  and rebuilt if its interpreter goes missing or falls below the floor.

## What breaks on 3.9

Syntax alone is not the test. `list[str] | None` in a signature parses on every
version but raises `TypeError` when the annotation is evaluated at def time,
which is why the app failed on a script the terminal ran happily:

```
TypeError: unsupported operand type(s) for |: 'types.GenericAlias' and 'NoneType'
```

`from __future__ import annotations` defers annotation evaluation and makes PEP
604 unions safe on 3.9. Modules using them must include it.

Safe on 3.9 without any import: builtin generics (`list[str]`, `dict[str, int]`,
PEP 585, landed in 3.9) and `zoneinfo`.

Not available at all: `match` statements, `dataclass(slots=True)`,
`itertools.pairwise`, `ExceptionGroup`, and `X | Y` outside an annotation.

`tests/test_python_compatibility.py` enforces both rules statically — it parses
each module with `feature_version` pinned to the floor and rejects union
annotations in modules that do not defer evaluation. It needs no dependencies
and no 3.9 interpreter, so it guards the floor from any machine.

## Verifying against a real 3.9

The static guard cannot catch a stdlib API that only exists in a later version.
Before a release, run the suite on the floor interpreter itself:

```bash
/usr/bin/python3 -m venv /tmp/venv39
/tmp/venv39/bin/pip install -r scripts/requirements.txt -r scripts/requirements-dev.txt
cd scripts && /tmp/venv39/bin/python3 -m pytest -q
```

## Open risk: /usr/bin/python3 is a stub

On a Mac with neither Xcode nor the Command Line Tools, `/usr/bin/python3` is a
shim that triggers the "install command line developer tools" dialog instead of
running. Apple ships no user-facing Python. So "no extra installs" holds for any
developer machine and for any user who has ever installed the tools, but not
necessarily for a clean install.

Resolving it means either bundling a Python runtime in the app (bigger download,
signing and notarization work) or porting the pipeline to Swift. Neither is
scheduled. Until then the app should detect the stub and say what to install
rather than failing with an opaque error.
