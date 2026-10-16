#!/usr/bin/env python3
"""
ingest-media.py
Copies a single source file into a flat working directory.

Usage: ingest-media.py <source_file> --target <working_dir> [--apply]

Source files are treated as read-only inputs — this script copies, never moves.
"""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys


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


def main():
    parser = argparse.ArgumentParser(
        description="Copy a single source file into a flat working directory."
    )
    parser.add_argument("file", help="Source file to ingest")
    parser.add_argument("--target", required=True,
                        help="Working directory to copy into")
    parser.add_argument("--companion-extensions", nargs="*", default=None,
                        help="Companion file extensions to copy alongside main file")
    parser.add_argument("--apply", action="store_true",
                        help="Apply changes (default: dry run)")

    args = parser.parse_args()

    if not os.path.isfile(args.file):
        print(f"ERROR: Source file not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    dest, action, companion_dests = ingest_file(
        args.file, args.target, args.apply,
        companion_extensions=args.companion_extensions,
    )
    print(f"@@dest={dest}")
    print(f"@@action={action}")
    for cd in companion_dests:
        print(f"@@companion={cd}")


if __name__ == "__main__":
    main()
