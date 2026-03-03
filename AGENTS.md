
- LAYOUT — three sibling projects at repo root. Each has their own AGENTS.md that may be read or updated as necessary if dealing with that project.
  - scripts/ — Python/shell scripts, lib/, media-profiles.yaml, tests/. Work standalone with no knowledge of the app.
  - macos/ — SwiftUI app. Sibling to scripts/, NOT nested inside it. Reads media-profiles.yaml and launches scripts.
  - web/ — Vite + Tailwind marketing site. Sections live in web/src/sections/.
  - docs/ — documentation. AGENTS.md, README.md, TODO.md live at repo root.
- don't reference Claude or AGENTS.md

- ARCHITECTURE
  - info at /docs/architecture.md
  - system overview, how components interact, profile system.
  - read and update as required

- ENVIRONMENT
 - info at /docs/environment.md
 - You may be in a MacOS or Linux environment. If commands don't work when you first run them, record which one works for which environment so you can check in there first.

- TESTING
 - info on testing best practices is at /docs/testing.md
 - This is required reading if dealing with any tests.

- COMMITS & PULL REQUESTS
 - info on commits and pull requests is stored at /docs/committing.md
 - this is required reading if dealing with any git or Github-based commands like commiting, branches, and creating pull requests.

- TODOs
  - a list of smaller TODOs are maintained at @docs/TODO.md, with larger tasks broken down into their own specifications in @docs/specs/, with previously completed ones in @docs/specs/completed.
  -  Large tasks in specs folder may not have their own entries in TODO.md, so part of looking for todos is checking through specs files as well. 
  - You don't need to open or consider completed specs in context, unless a history lesson would aid you to understand the why and how of a particular feature.
  - TODO.md is a sliding context window for fresh agents — open tasks only; completed work belongs in commit messages, not here
  - tasks are grouped by subrepo (`scripts/`, `macos/`, `web/`); cross-repo tasks appear under combined headings (e.g. `scripts/` + `macos/`)
  - each task is prefixed with its date added in YYYY-MM-DD format
  - at the start of each session, in the absence of any specific instruction, read TODO.md
  - if not instructed to work on a specific task, determine the single highest-leverage or most badly needed task, and work only on that.
  - Use dates created to help inform where we are up to in terms of the backlog and broken-down tasks that may only be partially implemented.
  - if a task is large enough, it can become a spec that requires its own MD. These can be placed in /docs/specs/. These can then similarly be worked through as part of a task or series of PRs, and then the file deleted as part of the final commit or PR in the series.
  - at the end of a session, remove any completed tasks from TODO.md and add any newly discovered ones.
  - If a linked spec file is now complete, move that markdown file into /docs/specs/implemented.
  - Never add a "Done" section or status reports to TODO.md, and never tick off items versus just removing them. The commit record is the 'Done' record. There should be no status updates in any files in the 'spec' folder.
