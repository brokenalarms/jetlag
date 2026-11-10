"""Asking the user before the pipeline does something they may not want."""

from __future__ import annotations

import sys


def require_consent(granted: bool, prompt: str, refusal_lines: list[str],
                    declined_line: str = "Cancelled.", stdin=None, stderr=None) -> None:
    """Go on only with the user's consent; otherwise exit 1.

    granted is consent already given by a flag. Without it, a real terminal is
    asked the y/n prompt (declined_line answers anything but y), and anything
    else is refused with refusal_lines, which say how to give consent.

    The prompt only ever runs on a real terminal. Reading stdin otherwise must
    never happen: under Xcode's Python input() opens /dev/tty regardless of where
    stdin points, and a non-interactive runner (tests, the app, a supervisor)
    reading the terminal from a background process group is stopped by SIGTTIN —
    the whole run freezes instead of failing.
    """
    if granted:
        return
    stdin = stdin or sys.stdin
    stderr = stderr or sys.stderr
    if stdin.isatty() and stderr.isatty():
        print(f"{prompt} (y/n) ", end="", file=stderr, flush=True)
        if stdin.readline().strip().lower() == "y":
            return
        print(declined_line, file=stderr)
        sys.exit(1)
    for line in refusal_lines:
        print(line, file=stderr)
    sys.exit(1)
