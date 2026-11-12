"""The working directory a run stages copies into, and what a cancel clears."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from lib.command_line import interrupt_handler

EXIFTOOL_TMP_GLOB = "*_exiftool_tmp"

# Staging lives on the target's own volume, so ingest is a single same-volume
# copy and organize's move is a rename rather than a second full copy across
# volumes. The destination's free space is then the only limit on a batch.
WORKING_DIR_NAME = ".jetlag-working"


class WorkingDir:
    """The staging directory and the copies in it the run currently owns.

    The working directory is an implementation detail: nothing survives in it past
    the iteration of the file it was staged for. The cancel handler closes over
    this object, so a cancel can take what the run owns with it.
    """

    def __init__(self, path: str = "", created: bool = False):
        self.path = path
        self.created = created
        self.staged: list[Path] = []

    def create(self) -> None:
        """Create the directory an apply stages into; a cancel now clears it.

        exiftool's scratch files left by a run that never reached its cancel
        handler (a crash, a destination that disconnected mid-write) are cleared
        too: exiftool refuses to write a file whose scratch file exists, and no
        exiftool is running for this run yet.
        """
        os.makedirs(self.path, exist_ok=True)
        self.created = True
        for leftover in self._exiftool_leftovers():
            print(f"🧹 Removing exiftool scratch file left by an earlier run: {leftover.name}",
                  file=sys.stderr)
            leftover.unlink()

    def _exiftool_leftovers(self) -> list[Path]:
        return sorted(Path(self.path).glob(EXIFTOOL_TMP_GLOB))

    def exists(self) -> bool:
        """Whether the directory is still there: it lives on the destination
        volume, so it goes when that volume disconnects."""
        return os.path.isdir(self.path)

    def stage(self, paths: list[Path]) -> None:
        """Record the working-dir copies this file's iteration owns."""
        self.staged = list(paths)

    def release(self) -> None:
        """Stop owning the staged copies without touching them: they have been
        moved out, or are kept for inspection after a failure."""
        self.staged = []

    def discard(self) -> None:
        """Delete the staged copies of the file being processed, if they still exist.

        The source is never touched — a staged copy organize declined to place is a
        duplicate with no further use.
        """
        for path in self.staged:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError as e:
                print(f"   ⚠️  Could not discard staged copy {path.name}: {e}", file=sys.stderr)
        self.staged = []

    def clean_on_cancel(self) -> None:
        """Leave nothing behind: the in-flight copies, exiftool's scratch files, the dir.

        Only safe once the metadata service has been closed, because until then
        exiftool may still be writing the very files this removes.
        """
        self.discard()
        if not self.created:
            return
        if not self.exists():
            return
        for leftover in self._exiftool_leftovers():
            try:
                leftover.unlink()
            except OSError:
                pass
        try:
            os.rmdir(self.path)
        except OSError:
            pass


def cancel_handler(working_dir: WorkingDir):
    """The SIGINT/SIGTERM handler for a run staging into working_dir.

    Cancel shuts exiftool down first; only then is the working directory quiet
    enough to clear.
    """
    return interrupt_handler(working_dir.clean_on_cancel)
