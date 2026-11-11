#!/bin/sh
# Run by the "Guard Worktree Bundle Identity" pre-build phase.
#
# A build in a linked worktree — .ralph/, .claude/worktrees/ or any other — the
# loop, a hands-on fix, a test run — otherwise carries exactly the identity of
# the app the user has installed: the same bundle id, the same product name, and
# so the same UserDefaults suite, the same Launch Services registration, the same
# ~/Library/Application Support folder and the same name in the Dock. A test host
# launched out of a worktree is then indistinguishable from the real app. The
# identity has to differ instead, so worktree builds pass the suffixes and this
# stops the ones that forget.
set -e

git_dir=$(git -C "${PROJECT_DIR}" rev-parse --path-format=absolute --git-dir 2>/dev/null) || exit 0
common_dir=$(git -C "${PROJECT_DIR}" rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || exit 0

if [ "${git_dir}" != "${common_dir}" ] && [ -z "${JETLAG_BUNDLE_SUFFIX:-}" ]; then
  echo "error: a build in a git worktree must carry a distinct identity so it never collides with the installed Jetlag. Use make build / make test-macos, or pass JETLAG_BUNDLE_SUFFIX=.dev JETLAG_PRODUCT_SUFFIX=\" Dev\" to xcodebuild."
  exit 1
fi
