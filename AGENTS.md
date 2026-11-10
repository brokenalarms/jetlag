
- LAYOUT — three sibling projects at repo root. Each has their own AGENTS.md that may be read or updated as necessary if dealing with that project.
  - scripts/ — Python/shell scripts, lib/, media-profiles.yaml, tests/. Work standalone with no knowledge of the app.
  - macos/ — SwiftUI app. Sibling to scripts/, NOT nested inside it. Reads media-profiles.yaml and launches scripts.
  - web/ — Vite + Tailwind marketing site. Sections live in web/src/sections/.
  - docs/ — documentation. AGENTS.md and README.md live at repo root.
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
 - If you are working on something that can be built or run in the environment, then a commit should not be made with the build in a broken state; eg all tests should pass, and the build should work (if you can verify)
 - E.g., in a MacOS environment for an Xcode project, part of allowing a commit would be that you have run `xcodegen generate` and built the project.

- COMMITS & PULL REQUESTS
 - info on commits and pull requests is stored at /docs/committing.md
 - this is required reading if dealing with any git or Github-based commands like commiting, branches, and creating pull requests.

- TASKS
  - tasks live in bd (beads): `bd ready` lists available work, `bd prime` explains the workflow. Commits for a tracked task carry its bead id, e.g. `[jetlag-xxx]`.
  - do not add tasks to docs/TODO.md.
  - larger designs get their own spec doc in /docs/specs/, worked through as a task or a series of PRs. When a spec is fully implemented, move it into /docs/specs/completed/ as part of the final commit or PR.
  - you don't need to open completed specs, unless a history lesson would help you understand the why and how of a feature.
  - specs carry no status updates, ticked boxes or "Done" sections. The commit record is the 'Done' record.
  - when bd is unavailable (e.g. Linux cloud sessions — see /docs/environment.md), work from /docs/specs/ and the user's instruction, and record any newly found tasks in the PR description instead.
  - if not instructed to work on a specific task, determine the single highest-leverage or most badly needed task, and work only on that.
