"""Shared filesystem utilities for media scripts."""

import errno
import os
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


def find_media_files(source_dir: str, extensions: list[str]) -> list[Path]:
    """Find all media files with given extensions, sorted alphabetically.

    Args:
        source_dir: Directory to search recursively
        extensions: List of file extensions to match (e.g., [".mp4", ".mov"])

    Returns:
        List of Path objects, deduplicated and sorted case-insensitively
    """
    source = Path(source_dir)
    files = []

    for ext in extensions:
        files.extend(source.rglob(f"*{ext}"))
        files.extend(source.rglob(f"*{ext.upper()}"))

    unique_files = list(set(files))
    unique_files.sort(key=lambda p: str(p).lower())

    return unique_files


def find_companions(source_file: Path, companion_extensions: list[str]) -> list[Path]:
    """Find companion files for a main file by matching stem with companion extensions.

    Checks both lowercase and uppercase versions of each extension.

    Args:
        source_file: Path to the main media file
        companion_extensions: List of extensions to look for (e.g., [".lrv", ".thm"])

    Returns:
        List of Path objects for existing companion files
    """
    stem = source_file.stem
    parent = source_file.parent
    companions = []

    for ext in companion_extensions:
        ext_lower = ext.lower()
        for candidate_ext in (ext_lower, ext_lower.upper()):
            candidate = parent / f"{stem}{candidate_ext}"
            if candidate.exists() and candidate != source_file:
                companions.append(candidate)

    return sorted(companions, key=lambda p: str(p).lower())


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
