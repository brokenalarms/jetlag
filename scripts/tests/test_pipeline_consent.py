"""
The pipeline asks before three things a user may not want: deleting stale
exiftool_tmp directories, importing protected files unlocked, and importing
files from another camera. All three go through require_consent, so these tests
pin its decisions once: a flag is consent, a terminal is asked, and anything
else is refused with the lines that say how to give consent. Refusal and a
declined prompt both exit 1; consent returns and prints nothing of its own.
"""

from __future__ import annotations

import io

import pytest

from lib.media_pipeline import require_consent


class _Stream(io.StringIO):
    """A text stream that says whether it is a terminal."""

    def __init__(self, text: str = "", tty: bool = False):
        super().__init__(text)
        self.tty = tty

    def isatty(self) -> bool:
        return self.tty


REFUSAL = ["ERROR: no consent.", "Re-run with --flag."]


def _ask(granted: bool, *, tty: bool, answer: str = ""):
    stdin, stderr = _Stream(answer, tty=tty), _Stream(tty=tty)
    try:
        require_consent(granted, "Go ahead?", REFUSAL, declined_line="Declined.",
                        stdin=stdin, stderr=stderr)
    except SystemExit as exit_info:
        return exit_info.code, stderr.getvalue()
    return None, stderr.getvalue()


def test_a_flag_is_consent_and_nothing_is_asked():
    """Actual: no exit, nothing written, even on a terminal
    Expected: --allow-camera-mismatch / --unlock-protected never prompt"""
    assert _ask(True, tty=True, answer="n\n") == (None, "")


def test_without_a_terminal_the_refusal_lines_are_printed_and_the_run_exits():
    """Actual: exit 1 with the refusal lines, no prompt
    Expected: the app and tests are never left waiting on stdin"""
    assert _ask(False, tty=False, answer="y\n") == (1, "ERROR: no consent.\nRe-run with --flag.\n")


@pytest.mark.parametrize("answer", ["y\n", "Y\n", "  y  \n"])
def test_a_terminal_answering_yes_goes_on(answer):
    """Actual: no exit, only the prompt was written
    Expected: a y in any case or padding is consent"""
    assert _ask(False, tty=True, answer=answer) == (None, "Go ahead? (y/n) ")


@pytest.mark.parametrize("answer", ["n\n", "\n", "yes\n"])
def test_a_terminal_answering_anything_else_declines(answer):
    """Actual: exit 1 after the prompt and the declined line
    Expected: only a plain y is consent"""
    assert _ask(False, tty=True, answer=answer) == (1, "Go ahead? (y/n) Declined.\n")
