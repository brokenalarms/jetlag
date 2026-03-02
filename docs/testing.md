# Testing

- Tests live in a `tests` subfolder within each of the projects.
- A commit can never be made with a known failing test, even if unrelated. It is the agent's responsibility to fix a failing test (by identifying regression that caused the failure, not just rewriting the test to pass) as soon as it is discovered. 
- at the time of writing tests, it's crucial to write out the meaning and the importance of the test explaining what it's trying to do in the form of a comment preceding the module or test. Use moduledoc for test classes, and individual test preamble comments where necessary.
-tests should not be updated to cater to broken behavior, unless we are specifically using TDD in advance to make a broken test then write the feature to fix itthe change.
- Otherwise tests at this stage should not break from a change unless there is a regression, and the test should be used to identify this regression.
 -testing that returncode is 0 is not testing the actual behavior or effect of the code, just that it ran without error, so would make for a useless test
 -similarly testing result.stdout reveals nothing but what the logs said, which could lie. the changes to the fake test file need to be recorded before and after with actual/expected human readable messages. Strings for users are brittle and should not be tested directly-that's why we have the scripts passing @@key=value for machines.
-Don't run the entire suite to validate every change. Try to run local relevant tests for that script or module first to avoid time wasted on redundant testing. Only perform a full test suite run if the work is complex or interrelated, or before the final push.
-Never re-run /scripts/tests if you have not made any changes inside /scripts, but if in the right environment (local MacOS only), always run /macos/tests if you made any changes inside of either /macos or /scripts.
-visually verify any web changes yourself in playwright if you can
-if you cannot visually build and verify (eg XCode projects), include on the PR a test plan checklist that the reviewer may follow to visually verify the changes in the live app.

- **Regression tests** — assert actual file state before and after, not just exit codes or stdout. Structured as "record before → run script → compare after" with human-readable expected vs actual diffs.
- **Performance tests** — snapshot harness. Runs media-pipeline end-to-end (3 files, fix-timestamp + organize), measures median wall-clock time over 3 runs, compares to a saved baseline. Threshold: 5% slower than baseline = regression. Delete the baseline file to re-record after intentional perf improvements.

Testing rules:
- Testing `returncode == 0` is not testing behavior — it only confirms the script didn't crash.
- Tests should not be updated without explicit confirmation unless following TDD (break test first, confirm expected failure, then update).
