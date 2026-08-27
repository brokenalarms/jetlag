#!/bin/sh
# Run by the "Guard Worktree Bundle Identity" pre-build phase.
#
# A build under .ralph/ — the loop, a hands-on fix, a test run — otherwise
# carries exactly the identity of the app the user has installed: the same
# bundle id, the same product name, and so the same UserDefaults suite, the same
# Launch Services registration, the same ~/Library/Application Support folder and
# the same name in the Dock. A test host launched out of a worktree is then
# indistinguishable from the real app. The identity has to differ instead, so
# worktree builds pass the suffixes and this stops the ones that forget.
set -e

case "${PROJECT_DIR}" in
  *"/.ralph/"*)
    if [ -z "${JETLAG_BUNDLE_SUFFIX:-}" ]; then
      echo "error: a build under .ralph/ must carry a distinct identity so it never collides with the installed Jetlag. Pass JETLAG_BUNDLE_SUFFIX=.dev JETLAG_PRODUCT_SUFFIX=\" Dev\" to xcodebuild."
      exit 1
    fi
    ;;
esac
