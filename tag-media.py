#!/usr/bin/env python3
"""
Tag media files with Finder tags and camera EXIF metadata
Extracted from import-media.py for reuse in media-pipeline
"""

import subprocess
import sys
import os
import signal
from pathlib import Path
from typing import List
import argparse

# Handle Ctrl-C gracefully
def signal_handler(sig, frame):  # noqa: ARG001
    print("\n\nInterrupted by user", file=sys.stderr)
    sys.exit(130)

signal.signal(signal.SIGINT, signal_handler)

def apply_finder_tags(file_path: str, tags: List[str]) -> bool:
    """Apply Finder tags to a file using macOS tag command"""
    if not tags:
        return True

    try:
        # Use tag command to apply tags
        for tag in tags:
            subprocess.run(['tag', '--add', tag, file_path],
                          capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Warning: Failed to apply tags to {file_path}: {e}", file=sys.stderr)
        return False

def add_camera_to_exif(file_path: str, camera: str) -> bool:
    """Add camera info to EXIF ImageDescription for Google Photos compatibility"""
    if not camera:
        return True

    # Only apply EXIF tags to supported file types (skip .lrv, .insv, etc.)
    # exiftool can handle these extensions without errors
    supported_extensions = {'.mp4', '.mov', '.jpg', '.jpeg', '.png', '.dng', '.arw', '.cr2', '.nef'}
    file_ext = Path(file_path).suffix.lower()

    if file_ext not in supported_extensions:
        return True  # Skip unsupported types silently

    try:
        subprocess.run([
            'exiftool', '-P', '-overwrite_original',
            f'-ImageDescription={camera}',
            f'-UserComment={camera}',
            file_path
        ], capture_output=True, check=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else str(e)
        print(f"Warning: Failed to add camera info to {file_path}: {error_msg}", file=sys.stderr)
        return False

def main():
    parser = argparse.ArgumentParser(description='Tag media files with Finder tags and camera EXIF')
    parser.add_argument('files', nargs='+', help='Media files to tag')
    parser.add_argument('--camera', help='Camera identifier to add to EXIF')
    parser.add_argument('--tags', help='Comma-separated Finder tags to apply')

    args = parser.parse_args()

    # Convert file paths to absolute paths to ensure exiftool can find them
    file_paths = [os.path.abspath(f) for f in args.files]

    # Parse tags
    finder_tags = args.tags.split(',') if args.tags else []

    success_count = 0
    for file_path in file_paths:
        if not os.path.exists(file_path):
            print(f"Warning: File not found: {file_path}", file=sys.stderr)
            continue

        # Apply camera EXIF
        if args.camera:
            if not add_camera_to_exif(file_path, args.camera):
                continue

            # Also apply camera as a Finder tag
            if not apply_finder_tags(file_path, [args.camera]):
                continue

        # Apply additional Finder tags
        if finder_tags:
            if not apply_finder_tags(file_path, finder_tags):
                continue

        success_count += 1

    if success_count < len(file_paths):
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
