#!/usr/bin/env python3
"""
archive-source.sh
Acts on the source directory after all pipeline files have been processed.

Command line for lib/archive_source.py; prints the result as @@key=value lines.

Modes:
  archive — move the source folder to <destination>/<archived-name>, defaulting
            to an in-place rename to "<source> - copied <YYYY-MM-DD>"
  delete  — remove the files passed via --files that verify-card matches on every
            --location, or that --accept names; keep and report the rest, then clean
            empty dirs
"""

import argparse
import os
import sys
from pathlib import Path

from cli.results import emit_result
from cli.verify_card import location_arg
from lib.archive_source import archive_source, delete_files
from lib.command_line import install_interrupt_handlers
from lib.exiftool import exiftool
from lib.verify_card import cleared_files, verify_card


def main():
    """Main entry point."""
    install_interrupt_handlers()

    parser = argparse.ArgumentParser(
        prog="archive-source.sh",
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
    verify = parser.add_argument_group(
        "delete", "A file is deleted only when verify-card matches it on every --location, "
                  "or --accept names it")
    verify.add_argument("--location", action="append", type=location_arg, default=[],
                        metavar="NAME=ROOT", help="A backup location to verify against; repeat for each")
    verify.add_argument("--media-extensions", nargs="+", default=[],
                        help="Extensions verify-card checks (required with --location)")
    verify.add_argument("--companion-extensions", nargs="*", default=[],
                        help="Extensions of companion files (.lrv, .thm ...)")
    verify.add_argument("--include-companions", action="store_true",
                        help="Verify companion files too, so they can be deleted")
    verify.add_argument("--ignore-paths", nargs="*", default=[],
                        help="Folder names verify-card does not check (e.g. MISC)")
    verify.add_argument("--accept", nargs="*", default=[],
                        help="Files to delete without verification: the user has accepted them")
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
        if not args.location and not args.accept:
            print("ERROR: delete needs --location to verify against, or --accept", file=sys.stderr)
            sys.exit(1)
        if args.location and not args.media_extensions:
            print("ERROR: --media-extensions is required with --location", file=sys.stderr)
            sys.exit(1)
        cleared = {Path(f).resolve() for f in args.accept}
        if args.location:
            try:
                report = verify_card(Path(source), args.location, args.media_extensions,
                                     args.companion_extensions, args.include_companions,
                                     args.ignore_paths)
            finally:
                exiftool.close()
            cleared |= cleared_files(report, Path(source))
        result = delete_files(source, args.files, args.apply, cleared)
        emit_result(result)
        sys.exit(1 if result.failed else 0)


if __name__ == "__main__":
    main()
