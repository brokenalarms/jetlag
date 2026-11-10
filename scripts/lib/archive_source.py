"""Act on the source directory once every pipeline file has been processed.

archive — move the source folder to <destination>/<archived-name>, defaulting
          to an in-place rename to "<source> - copied <YYYY-MM-DD>"
delete  — remove only the files given, then clean up emptied directories
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from lib.filesystem import cleanup_empty_parent_dirs


@dataclass
class ArchiveResult:
    action: str  # "archived" | "deleted" | "would_archive" | "would_delete"
    failed: bool


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
