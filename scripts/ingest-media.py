#!/usr/bin/env python3
"""
ingest-media.py
Copies a single source file into a flat working directory.

Usage: ingest-media.py <source_file> --target <working_dir> [--apply]

Command line for lib/ingest.py. Source files are treated as read-only inputs —
this script copies, never moves.
"""

from __future__ import annotations

import argparse
import os
import sys

from lib.ingest import ingest_file


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
