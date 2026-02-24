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


def ingest_file(source_file: str, target_dir: str, apply: bool) -> tuple[str, str]:
    """Copy a single source file into a flat working directory.

    Returns:
        (dest_path, action) tuple
    """
    filename = os.path.basename(source_file)
    dest = os.path.join(target_dir, filename)

    if apply:
        os.makedirs(target_dir, exist_ok=True)
        shutil.copy2(source_file, dest)
        print(f"Copied: {source_file} → {dest}", file=sys.stderr)
        return dest, "copied"
    else:
        print(f"[DRY RUN] Would copy: {source_file} → {dest}", file=sys.stderr)
        return dest, "would_copy"


def main():
    parser = argparse.ArgumentParser(
        description="Copy a single source file into a flat working directory."
    )
    parser.add_argument("file", help="Source file to ingest")
    parser.add_argument("--target", required=True,
                        help="Working directory to copy into")
    parser.add_argument("--apply", action="store_true",
                        help="Apply changes (default: dry run)")

    args = parser.parse_args()

    if not os.path.isfile(args.file):
        print(f"ERROR: Source file not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    dest, action = ingest_file(args.file, args.target, args.apply)
    print(f"@@dest={dest}")
    print(f"@@action={action}")


if __name__ == "__main__":
    main()
