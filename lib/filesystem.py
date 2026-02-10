"""Shared filesystem utilities for media scripts."""

import errno
import os


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
