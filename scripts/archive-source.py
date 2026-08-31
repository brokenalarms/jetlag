#!/usr/bin/env python3
"""
archive-source.py
Acts on the source directory after all pipeline files have been processed.

Modes:
  archive — move the source folder to <destination>/<archived-name>, defaulting
            to an in-place rename to "<source> - copied <YYYY-MM-DD>"
  delete  — remove only the files passed via --files, then clean empty dirs
"""

import argparse
import os
import signal
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from lib.filesystem import cleanup_empty_parent_dirs
from lib.results import emit_result


@dataclass
class ArchiveResult:
    action: str  # "archived" | "deleted" | "would_archive" | "would_delete"
    failed: bool


def signal_handler(sig, frame):
    """Handle Ctrl-C gracefully."""
    print("\n\nInterrupted by user", file=sys.stderr)
    sys.exit(130)


def default_archived_name(source: str, today: Optional[datetime] = None) -> str:
    """The name an archived folder takes when the caller names none."""
    current_date = (today or datetime.now()).strftime("%Y-%m-%d")
    return f"{os.path.basename(os.path.normpath(source))} - copied {current_date}"


def archive_source(
    source: str,
    apply: bool,
    destination: Optional[str] = None,
    archived_name: Optional[str] = None,
) -> ArchiveResult:
    """Move the source folder to destination/archived_name.

    Both parts default to today's in-place archive: the folder stays beside
    where it was and takes the name '<source> - copied <date>'.
    """
    parent = destination or os.path.dirname(os.path.abspath(os.path.normpath(source)))
    name = archived_name or default_archived_name(source)
    target = os.path.join(parent, name)

    if not apply:
        print(f"Would rename: {source} → {target}", file=sys.stderr)
        return ArchiveResult(action="would_archive", failed=False)

    try:
        os.rename(source, target)
        print(f"Archived: {source} → {target}", file=sys.stderr)
        return ArchiveResult(action="archived", failed=False)
    except OSError as e:
        print(f"Read-only source, couldn't archive: {source} ({e})", file=sys.stderr)
        return ArchiveResult(action="archived", failed=True)


def delete_files(source: str, files: list[str], apply: bool) -> ArchiveResult:
    """Delete listed files from source, then clean up empty directories."""
    if not files:
        print("No files to delete", file=sys.stderr)
        return ArchiveResult(action="would_delete" if not apply else "deleted", failed=False)

    failed = False

    for file_path in files:
        if not os.path.exists(file_path):
            continue

        if not apply:
            print(f"Would delete: {os.path.relpath(file_path, source)}", file=sys.stderr)
            continue

        try:
            os.remove(file_path)
            print(f"Deleted: {os.path.relpath(file_path, source)}", file=sys.stderr)
        except OSError as e:
            print(f"Read-only source, couldn't delete: {file_path} ({e})", file=sys.stderr)
            failed = True

    # Clean up empty directories (only in apply mode)
    if apply:
        cleaned_dirs = set()
        for file_path in files:
            parent = os.path.dirname(file_path)
            if parent not in cleaned_dirs and parent != source:
                cleanup_empty_parent_dirs(parent, stop_at=source)
                cleaned_dirs.add(parent)

    return ArchiveResult(
        action="would_delete" if not apply else "deleted",
        failed=failed,
    )


def main():
    """Main entry point."""
    signal.signal(signal.SIGINT, signal_handler)

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
