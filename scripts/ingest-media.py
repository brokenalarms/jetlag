#!/usr/bin/env python3
"""
ingest-media.py
Copies a single source file into a flat working directory.

Usage: ingest-media.py <source_file> --target <working_dir> [--apply]

Source files are treated as read-only inputs — this script copies, never moves.
"""

import argparse
import os
import shutil
import sys


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
        shutil.copy2(source_file, dest)
        print(f"Copied: {source_file} → {dest}", file=sys.stderr)
        action = "copied"
    else:
        print(f"[DRY RUN] Would copy: {source_file} → {dest}", file=sys.stderr)
        action = "would_copy"

    if companion_extensions:
        source_dir = os.path.dirname(source_file)
        stem = os.path.splitext(filename)[0]
        for ext in companion_extensions:
            companion_source = os.path.join(source_dir, stem + ext)
            if os.path.isfile(companion_source):
                companion_dest = os.path.join(target_dir, stem + ext)
                if apply:
                    shutil.copy2(companion_source, companion_dest)
                    print(f"Copied companion: {companion_source} → {companion_dest}", file=sys.stderr)
                else:
                    print(f"[DRY RUN] Would copy companion: {companion_source} → {companion_dest}", file=sys.stderr)
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
