# Committing, branches & pull requests

## Session start — branch check

Before any commit or push action, every session:

1. for new features, ALWAYS create a worktree. You may have already been invoked in one, but ALWAYS check first and ALWAYS create a worktree for a new session.
2. `git fetch origin main` then `git log origin/main --oneline | head -10`
3. If a recent main commit title matches the session-assigned branch name or task (squash-merged indicator), the old branch is dead — **immediately** `git checkout -b claude/<new-descriptive-name>-<session-token> origin/main` before touching any files
4. Never do any work on a branch that was squash-merged; GitHub closes that branch's PR and new commits become inaccessible through it
5. **`git branch -r --merged` does NOT detect squash merges** — always use the commit title comparison method above
6. you don't need to ask for permission to pull new content in from main and run local git commands, besides final pushes.

## Commits

- Before **every** commit, repeat the branch check above — merges can land between commits
- Commits should be atomic: one feature change or bug fix per commit where possible
- Every commit message must have a subject line AND a body separated by a blank line — GitHub uses the subject as PR title and body as PR description when the user clicks "Create PR" on the branch
- Commit body: concise bullet list covering **why** (the bug or goal), **how** (the approach), and test coverage. Filenames are fine; variable/struct names only when they clarify a concept. Don't narrate the diff — the reader has it open.
- Related atomic commits may be grouped into a single PR
- Every commit that changes code for a feature or bug fix must be backed by a test covering that change
- Never commit without first running tests with `pytest -x` and confirming they pass
- One branch per PR — never reuse a branch that has already been merged into main; create a new branch for each new PR
- When a PR completes a step in a multi-step task tracked in `TODO.md` or `todos/`, include updates to those files in the same PR: mark completed sub-steps in the `todos/*.md` spec and strike/update the corresponding entry in `TODO.md`. The tracking files should always reflect reality after each merge, not only at the end of the full task.

## Pull requests

- After pushing, always create the PR with `gh pr create` if available — this supports full markdown bodies without URL-encoding issues
- Otherwise, provide a fully URL-encoded link for user to click on to create PR
- PR title and body follow the same format as commit messages: imperative title (lowercase, no period), concise bullet-list body covering **why**, **how**, and test coverage. The PR description should encapsulate the sum of all commits in the PR, not repeat each one individually.
- If subsequent commits are added to a PR, update the PR title/body with `gh pr edit` to reflect the full scope of changes. If `gh` is unavailable, give the user new description text to paste in.
  