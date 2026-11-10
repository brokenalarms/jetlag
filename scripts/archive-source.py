#!/usr/bin/env python3
"""
archive-source.py
Acts on the source directory after all pipeline files have been processed.

Command line for lib/archive.py; prints the result as @@key=value lines.

Modes:
  archive — move the source folder to <destination>/<archived-name>, defaulting
            to an in-place rename to "<source> - copied <YYYY-MM-DD>"
  delete  — remove only the files passed via --files, then clean empty dirs
"""

import argparse
import os
import sys

from lib.archive import archive_source, delete_files
from lib.cli import install_interrupt_handlers
from lib.results import emit_result


def main():
    """Main entry point."""
    install_interrupt_handlers()

    parser = argparse.ArgumentParser(
        description="Act on source directory after pipeline processing."
    )
    parser.add_argument("--source", required=True, help="Source directory to act on")
    parser.add_argument(
        "--action",
        choices=["archive", "delete"],
        default="archive",
        help="Action to take on source (default: archive)",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=[],
        help="File paths to delete (required for delete action)",
    )
    parser.add_argument(
        "--destination",
        help="Directory to move the archived folder into (default: where the source already is)",
    )
    parser.add_argument(
        "--archived-name",
        help="Name for the archived folder (default: '<source> - copied <YYYY-MM-DD>')",
    )
    parser.add_argument("--apply", action="store_true", help="Apply changes (default: dry run)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed info")

    args = parser.parse_args()

    source = args.source

    if not os.path.isdir(source):
        print(f"ERROR: Source directory not found: {source}", file=sys.stderr)
        sys.exit(1)

    if args.action == "archive":
        result = archive_source(
            source, args.apply,
            destination=args.destination,
            archived_name=args.archived_name,
        )
        emit_result(result)
        sys.exit(1 if result.failed else 0)

    if args.action == "delete":
        if not args.files:
            print("ERROR: --files is required for delete action", file=sys.stderr)
            sys.exit(1)
        result = delete_files(source, args.files, args.apply)
        emit_result(result)
        sys.exit(1 if result.failed else 0)


if __name__ == "__main__":
    main()
