
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
 - If you are working on something that can be built or run in the environment, then a commit should not be made with the build in a broken state; eg all tests should pass, and the build should work (if you can verify)
 - E.g., in a MacOS environment for an Xcode project, part of allowing a commit would be that you have run `xcodegen generate` and built the project.

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

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:970c3bf2 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Agent Context Profiles

The managed Beads block is task-tracking guidance, not permission to override repository, user, or orchestrator instructions.

- **Conservative (default)**: Use `bd` for task tracking. Do not run git commits, git pushes, or Dolt remote sync unless explicitly asked. At handoff, report changed files, validation, and suggested next commands.
- **Minimal**: Keep tool instruction files as pointers to `bd prime`; use the same conservative git policy unless active instructions say otherwise.
- **Team-maintainer**: Only when the repository explicitly opts in, agents may close beads, run quality gates, commit, and push as part of session close. A current "do not commit" or "do not push" instruction still wins.

## Session Completion

This protocol applies when ending a Beads implementation workflow. It is subordinate to explicit user, repository, and orchestrator instructions.

1. **File issues for remaining work** - Create beads for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **Handle git/sync by active profile**:
   ```bash
   # Conservative/minimal/default: report status and proposed commands; wait for approval.
   git status

   # Team-maintainer opt-in only, unless current instructions forbid it:
   git pull --rebase
   bd dolt push
   git push
   git status
   ```
5. **Hand off** - Summarize changes, validation, issue status, and any blocked sync/commit/push step

**Critical rules:**
- Explicit user or orchestrator instructions override this Beads block.
- Do not commit or push without clear authority from the active profile or the current user request.
- If a required sync or push is blocked, stop and report the exact command and error.
<!-- END BEADS INTEGRATION -->

<!-- BEGIN BEADS CODEX SETUP: generated by bd setup codex -->
## Beads Issue Tracker

Use Beads (`bd`) for durable task tracking in repositories that include it. Use the `beads` skill at `.agents/skills/beads/SKILL.md` (project install) or `~/.agents/skills/beads/SKILL.md` (global install) for Beads workflow guidance, then use the `bd` CLI for issue operations.

### Quick Reference

```bash
bd ready                # Find available work
bd show <id>            # View issue details
bd update <id> --claim  # Claim work
bd close <id>           # Complete work
bd prime                # Refresh Beads context
```

### Rules

- Use `bd` for all task tracking; do not create markdown TODO lists.
- Run `bd prime` when Beads context is missing or stale. Codex 0.129.0+ can load Beads context automatically through native hooks; use `/hooks` to inspect or toggle them.
- Keep persistent project memory in Beads via `bd remember`; do not create ad hoc memory files.

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.
<!-- END BEADS CODEX SETUP -->
