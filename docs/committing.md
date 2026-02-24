# Committing, branches & pull requests

## Session start — branch check

Before any commit or push action, every session:

1. `git fetch origin main` then `git log origin/main --oneline | head -10`
2. If a recent main commit title matches the session-assigned branch name or task (squash-merged indicator), the old branch is dead — **immediately** `git checkout -b claude/<new-descriptive-name>-<session-token> origin/main` before touching any files
3. Never do any work on a branch that was squash-merged; GitHub closes that branch's PR and new commits become inaccessible through it
4. **`git branch -r --merged` does NOT detect squash merges** — always use the commit title comparison method above

## Commits

- Before **every** commit, repeat the branch check above — merges can land between commits
- Commits should be atomic: one feature change or bug fix per commit where possible
- Every commit message must have a subject line AND a body separated by a blank line — GitHub uses the subject as PR title and body as PR description when the user clicks "Create PR" on the branch
- Commit body should cover: what changed, why, and how it was tested
- Related atomic commits may be grouped into a single PR
- Every commit that changes code for a feature or bug fix must be backed by a test covering that change
- Never commit without first running tests with `pytest -x` and confirming they pass
- One branch per PR — never reuse a branch that has already been merged into main; create a new branch for each new PR

## Pull requests

- After pushing, always create the PR with `gh pr create` — this supports full markdown bodies without URL-encoding issues
- Title: imperative sentence, lowercase, no period — what changed, not what you did
- Body: concise but informative bullet points covering **what** changed, **why**, and **how it was tested**. Group by theme (e.g. new files, modified behavior, test changes). The reader should understand the PR without opening every file
- If subsequent commits are added to a PR, update the PR title/body with `gh pr edit` to describe the full series of commits