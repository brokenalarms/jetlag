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

    source_file = args.file
    target_dir = args.target

    if not os.path.isfile(source_file):
        print(f"ERROR: Source file not found: {source_file}", file=sys.stderr)
        sys.exit(1)

    filename = os.path.basename(source_file)
    dest = os.path.join(target_dir, filename)

    if args.apply:
        os.makedirs(target_dir, exist_ok=True)
        shutil.copy2(source_file, dest)
        print(f"Copied: {source_file} → {dest}", file=sys.stderr)
        print(f"@@dest={dest}")
        print(f"@@action=copied")
    else:
        print(f"[DRY RUN] Would copy: {source_file} → {dest}", file=sys.stderr)
        print(f"@@dest={dest}")
        print(f"@@action=would_copy")


if __name__ == "__main__":
    main()
