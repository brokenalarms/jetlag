"""Copy one source file (and its companions) into the flat working directory.

Source files are read-only inputs: ingest copies, never moves.
"""

from __future__ import annotations

import os
import shutil
import stat


def is_protected(path: str) -> bool:
    """Whether path carries the user-immutable flag — Finder's "Locked", and
    what a camera's "Protect" arrives as on macOS."""
    return hasattr(os, "chflags") and bool(os.stat(path).st_flags & stat.UF_IMMUTABLE)


def stage_copy(source: str, dest: str) -> None:
    """copy2, minus the user-immutable flag copystat carries across.

    The staged copy is the pipeline's scratch file — later stages rewrite its
    metadata and move it — so a lock carried onto it fails each of those with
    EPERM. The source keeps its flag.
    """
    shutil.copy2(source, dest)
    if is_protected(dest):
        os.chflags(dest, os.stat(dest).st_flags & ~stat.UF_IMMUTABLE)


def ingest_file(
    source_file: str,
    target_dir: str,
    apply: bool,
    companion_extensions: list[str] | None = None,
) -> tuple[str, str, list[str]]:
    """Copy a single source file into a flat working directory.

    When companion_extensions is provided, also copies files with the same stem
    and matching extensions from the source directory.

    Returns:
        (dest_path, action, companion_dests) tuple
    """
    filename = os.path.basename(source_file)
    dest = os.path.join(target_dir, filename)

    companion_dests = []

    if apply:
        os.makedirs(target_dir, exist_ok=True)
        stage_copy(source_file, dest)
        action = "copied"
    else:
        action = "would_copy"

    if companion_extensions:
        source_dir = os.path.dirname(source_file)
        stem = os.path.splitext(filename)[0]
        for ext in companion_extensions:
            companion_source = os.path.join(source_dir, stem + ext)
            if os.path.isfile(companion_source):
                companion_dest = os.path.join(target_dir, stem + ext)
                if apply:
                    stage_copy(companion_source, companion_dest)
                companion_dests.append(companion_dest)

    return dest, action, companion_dests
