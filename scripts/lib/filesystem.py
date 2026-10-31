"""Shared filesystem utilities for media scripts."""

import errno
import os
from collections.abc import Iterator
from pathlib import Path


def cleanup_empty_parent_dirs(file_dir: str, stop_at: str) -> None:
    """Remove empty parent directories after moving a file.

    Walks up from file_dir, removing empty directories. Stops BEFORE stop_at
    (never removes it). Removes .DS_Store files if they're the only thing
    preventing directory cleanup.

    Args:
        file_dir: Directory the file was moved from
        stop_at: Boundary directory to stop before (never removed)
    """
    stop_at = os.path.realpath(stop_at)
    cwd = os.path.realpath('.')

    while file_dir and file_dir != '/' and file_dir != '.':
        file_dir = os.path.realpath(file_dir)

        if file_dir == cwd:
            break

        if file_dir == stop_at:
            break

        # Remove .DS_Store if it's the only thing preventing cleanup
        ds_store = os.path.join(file_dir, '.DS_Store')
        if os.path.isfile(ds_store):
            entries = os.listdir(file_dir)
            if entries == ['.DS_Store']:
                os.remove(ds_store)

        try:
            os.rmdir(file_dir)
            file_dir = os.path.dirname(file_dir)
        except OSError as e:
            if e.errno in (errno.ENOTEMPTY, errno.EEXIST):
                break
            print(f"Warning: Could not remove empty directory {file_dir}: {e}",
                  file=__import__('sys').stderr)
            break


# Folders macOS presents as a single file. Their contents are another app's data,
# not a camera's originals, and reading into a Photos library asks the user for
# Photos access they never meant to give.
PACKAGE_SUFFIXES = {".photoslibrary", ".app", ".bundle", ".fcpbundle", ".imovielibrary",
                    ".tvlibrary", ".lrlibrary", ".lrdata", ".cocatalog"}


def _is_walked(name: str) -> bool:
    return not name.startswith(".") and Path(name).suffix.lower() not in PACKAGE_SUFFIXES


def iter_media_files(source_dir: str, extensions: list[str]) -> Iterator[Path]:
    """Yield media files with the given extensions as one walk finds them.

    Hidden entries are skipped, which includes the ._ files exFAT cards gain
    beside each clip, as are packages. Extensions match in any case.
    """
    wanted = {ext.lower() for ext in extensions}
    for directory, dirs, files in os.walk(source_dir):
        dirs[:] = [d for d in dirs if _is_walked(d)]
        for name in files:
            if not name.startswith(".") and Path(name).suffix.lower() in wanted:
                yield Path(directory) / name


def find_media_files(source_dir: str, extensions: list[str]) -> list[Path]:
    """Find all media files with given extensions, sorted case-insensitively by path.

    Args:
        source_dir: Directory to search recursively
        extensions: List of file extensions to match (e.g., [".mp4", ".mov"])

    Returns:
        List of Path objects, deduplicated and sorted case-insensitively
    """
    return sorted(set(iter_media_files(source_dir, extensions)), key=lambda p: str(p).lower())


def parse_machine_output(stdout: str) -> dict:
    """Parse machine-readable @@key=value lines from subprocess stdout.

    Args:
        stdout: Raw stdout string from a subprocess

    Returns:
        Dict of key-value pairs parsed from @@key=value lines
    """
    result = {}
    for line in stdout.strip().split('\n'):
        if line.startswith('@@') and '=' in line:
            key, value = line[2:].split('=', 1)
            result[key] = value
    return result
