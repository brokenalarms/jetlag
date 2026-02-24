- DOCS — read the relevant doc before working on a component:
  - docs/scripts.md: when working on anything in scripts/
  - docs/macos.md: when working on the Jetlag macOS app
  - docs/web.md: when working on the marketing site
  - docs/architecture.md: system overview, how components interact, profile system
  - TODO.md: sliding context window — read at session start, pick ONE task
- SESSION START — before any other action, every session:
  1. `git fetch origin main` then `git log origin/main --oneline | head -10`
  2. If a recent main commit title matches the session-assigned branch name or task (squash-merged indicator), the old branch is dead — **immediately** `git checkout -b claude/<new-descriptive-name>-<session-token> origin/main` before touching any files
  3. Never do any work on a branch that was squash-merged; GitHub closes that branch's PR and new commits become inaccessible through it
  4. **`git branch -r --merged` does NOT detect squash merges** — always use the commit title comparison method above
- LAYOUT — three sibling components at repo root:
  - scripts/ — Python/shell scripts, lib/, media-profiles.yaml, tests/. Work standalone with no knowledge of the app.
  - macos/ — SwiftUI app. Sibling to scripts/, NOT nested inside it. Reads media-profiles.yaml and launches scripts.
  - web/ — Vite + Tailwind marketing site. Sections live in web/src/sections/.
  - docs/ — documentation. CLAUDE.md, README.md, TODO.md live at repo root.
- don't reference Claude or Claude.md
- TESTING
  - every commit that changes code for a feature or bug fix must be backed by a test covering that change
  - tests must be run before committing any code change — do not commit if tests fail
  - always run tests with fail fast: `pytest -x` (stop on first failure and address one at a time before continuing)
  - tests should not be updated without explicit confirmation, unless we use TDD to make the change, confirm that the the tests now break in the way expected, then update the test accordingly. Otherwise tests at this stage should not break from a change unless there is a regression, and the test should be used to identify this regression.
  - testing that returncode is 0 is not testing the actual behavior or effect of the code, just that it ran without error, so would make for a useless test
  - simarly testing result.stdout reveals nothing but what the logs said, which could lie. the changes to the fake test file need to be recorded before and after with actual/expected human readable messages.
- COMMITS
  - before **every** commit, repeat the session-start branch check (see SESSION START above) — merges can land between commits
  - commits should be atomic: one feature change or bug fix per commit where possible
  - every commit message must have a subject line AND a body separated by a blank line — GitHub uses the subject as PR title and body as PR description when the user clicks "Create PR" on the branch
  - commit body should cover: what changed, why, and how it was tested
  - related atomic commits may be grouped into a single PR
  - never commit without first running tests with `pytest -x` and confirming they pass
  - one branch per PR — never reuse a branch that has already been merged into main; create a new branch for each new PR
- PULL REQUESTS
  - after pushing, always output a pre-filled GitHub compare URL so the user can open a PR with one click; generate it with python so every character is properly escaped:
    ```
    python3 -c "import urllib.parse; t='<title>'; b='<one sentence body>'; print('https://github.com/brokenalarms/Jetlag/compare/<branch>?expand=1&title='+urllib.parse.quote(t,safe='')+'&body='+urllib.parse.quote(b,safe=''))"
    ```
  - keep the URL body to one short plain sentence with no newlines and no trailing period — dots at the end of URLs get stripped by markdown parsers. GitHub will override with the commit body anyway for single-commit branches
  - title: imperative sentence, lowercase, no period — what changed, not what you did
- TODO.md
  - TODO.md is a sliding context window for fresh agents — open tasks only; completed work belongs in commit messages, not here
  - tasks are grouped by subrepo (`scripts/`, `macos/`, `web/`); cross-repo tasks appear under combined headings (e.g. `scripts/` + `macos/`)
  - each task is prefixed with its date added in YYYY-MM-DD format
  - at the start of each session, read TODO.md; if not instructed to work on a specific task, determine the single highest-leverage, oldest, or most badly needed task, and work only on that
  - at the end of a session, remove completed tasks and add any newly discovered ones; never add a "Done" section
