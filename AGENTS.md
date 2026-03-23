
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

<!-- BEGIN BEADS INTEGRATION -->
## Issue Tracking with bd (beads)

**IMPORTANT**: This project uses **bd (beads)** for ALL issue tracking. Do NOT use markdown TODOs, task lists, or other tracking methods.

### Why bd?

- Dependency-aware: Track blockers and relationships between issues
- Git-friendly: Dolt-powered version control with native sync
- Agent-optimized: JSON output, ready work detection, discovered-from links
- Prevents duplicate tracking systems and confusion

### Quick Start

**Check for ready work:**

```bash
bd ready --json
```

**Create new issues:**

```bash
bd create "Issue title" --description="Detailed context" -t bug|feature|task -p 0-4 --json
bd create "Issue title" --description="What this issue is about" -p 1 --deps discovered-from:bd-123 --json
```

**Claim and update:**

```bash
bd update <id> --claim --json
bd update bd-42 --priority 1 --json
```

**Complete work:**

```bash
bd close bd-42 --reason "Completed" --json
```

### Issue Types

- `bug` - Something broken
- `feature` - New functionality
- `task` - Work item (tests, docs, refactoring)
- `epic` - Large feature with subtasks
- `chore` - Maintenance (dependencies, tooling)

### Priorities

- `0` - Critical (security, data loss, broken builds)
- `1` - High (major features, important bugs)
- `2` - Medium (default, nice-to-have)
- `3` - Low (polish, optimization)
- `4` - Backlog (future ideas)

### Workflow for AI Agents

1. **Check ready work**: `bd ready` shows unblocked issues
2. **Claim your task atomically**: `bd update <id> --claim`
3. **Work on it**: Implement, test, document
4. **Discover new work?** Create linked issue:
   - `bd create "Found bug" --description="Details about what was found" -p 1 --deps discovered-from:<parent-id>`
5. **Complete**: `bd close <id> --reason "Done"`

### Auto-Sync

bd automatically syncs via Dolt:

- Each write auto-commits to Dolt history
- Use `bd dolt push`/`bd dolt pull` for remote sync
- No manual export/import needed!

### Important Rules

- ✅ Use bd for ALL task tracking
- ✅ Always use `--json` flag for programmatic use
- ✅ Link discovered work with `discovered-from` dependencies
- ✅ Check `bd ready` before asking "what should I work on?"
- ❌ Do NOT create markdown TODO lists
- ❌ Do NOT use external issue trackers
- ❌ Do NOT duplicate tracking systems

For more details, see README.md and docs/QUICKSTART.md.

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds

<!-- END BEADS INTEGRATION -->
