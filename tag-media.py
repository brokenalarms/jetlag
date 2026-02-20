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
from typing import List, Optional, Tuple
import argparse

# Handle Ctrl-C gracefully
def signal_handler(sig, frame):  # noqa: ARG001
    print("\n\nInterrupted by user", file=sys.stderr)
    sys.exit(130)

signal.signal(signal.SIGINT, signal_handler)

def get_existing_finder_tags(file_path: str) -> List[str]:
    """Get existing Finder tags from a file"""
    try:
        result = subprocess.run(['tag', '--list', '--no-name', file_path],
                              capture_output=True, check=True, text=True)
        # Parse tags - comma-separated on a single line
        output = result.stdout.strip()
        if not output:
            return []
        existing_tags = [tag.strip() for tag in output.split(',') if tag.strip()]
        return existing_tags
    except subprocess.CalledProcessError:
        return []

def apply_finder_tags(file_path: str, tags: List[str], dry_run: bool = False) -> Tuple[bool, List[str]]:
    """Apply Finder tags to a file using macOS tag command

    Returns:
        (success, tags_added): Success status and list of tags that were actually added
    """
    if not tags:
        return True, []

    try:
        # Check which tags already exist
        existing_tags = get_existing_finder_tags(file_path)
        tags_to_add = [tag for tag in tags if tag not in existing_tags]

        if not tags_to_add:
            return True, []  # All tags already present

        # Use tag command to add only missing tags (unless dry run)
        if not dry_run:
            subprocess.run(['tag', '--add', ','.join(tags_to_add), file_path],
                          capture_output=True, check=True)
        return True, tags_to_add
    except subprocess.CalledProcessError as e:
        print(f"Warning: Failed to apply tags to {file_path}: {e}", file=sys.stderr)
        return False, []

def get_existing_exif_camera(file_path: str) -> dict:
    """Get existing Make and Model from EXIF data"""
    try:
        result = subprocess.run(['exiftool', '-s', '-Make', '-Model', file_path],
                              capture_output=True, check=True, text=True)

        data = {}
        for line in result.stdout.strip().split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()
                data[key] = value

        return data
    except subprocess.CalledProcessError:
        return {}

def add_camera_to_exif(file_path: str, make: Optional[str] = None, model: Optional[str] = None, dry_run: bool = False) -> Tuple[bool, List[str]]:
    """Add camera info to EXIF Make and Model fields

    Returns:
        (success, fields_updated): Success status and list of fields that were actually updated
    """
    if not make and not model:
        return True, []

    # Only apply EXIF tags to supported file types (skip .lrv, .insv, etc.)
    # exiftool can handle these extensions without errors
    supported_extensions = {'.mp4', '.mov', '.jpg', '.jpeg', '.png', '.dng', '.arw', '.cr2', '.nef'}
    file_ext = Path(file_path).suffix.lower()

    if file_ext not in supported_extensions:
        return True, []  # Skip unsupported types silently

    try:
        # Check existing EXIF data
        existing = get_existing_exif_camera(file_path)

        # Determine what needs updating
        fields_to_update = []
        cmd = ['exiftool', '-P', '-overwrite_original']

        if make and existing.get('Make') != make:
            cmd.append(f'-Make={make}')
            fields_to_update.append('Make')

        if model and existing.get('Model') != model:
            cmd.append(f'-Model={model}')
            fields_to_update.append('Model')

        if not fields_to_update:
            return True, []  # All fields already correct

        # Only run exiftool if not dry run
        if not dry_run:
            cmd.append(file_path)
            subprocess.run(cmd, capture_output=True, check=True, text=True)
        return True, fields_to_update
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else str(e)
        print(f"Warning: Failed to add camera info to {file_path}: {error_msg}", file=sys.stderr)
        return False, []

def main():
    parser = argparse.ArgumentParser(description='Tag media files with Finder tags and camera EXIF')
    parser.add_argument('files', nargs='+', help='Media files to tag')
    parser.add_argument('--make', help='Camera make/manufacturer to add to EXIF')
    parser.add_argument('--model', help='Camera model to add to EXIF')
    parser.add_argument('--tags', help='Comma-separated Finder tags to apply')
    parser.add_argument('--apply', action='store_true', help='Apply changes (default: dry run)')

    args = parser.parse_args()
    dry_run = not args.apply

    # Convert file paths to absolute paths to ensure exiftool can find them
    file_paths = [os.path.abspath(f) for f in args.files]

    # Parse tags
    finder_tags = args.tags.split(',') if args.tags else []

    success_count = 0
    for file_path in file_paths:
        if not os.path.exists(file_path):
            print(f"Warning: File not found: {file_path}", file=sys.stderr)
            continue

        filename = os.path.basename(file_path)
        actions = []

        # Apply camera EXIF (Make and Model)
        if args.make or args.model:
            success, fields_updated = add_camera_to_exif(file_path, make=args.make, model=args.model, dry_run=dry_run)
            if not success:
                continue

            if fields_updated:
                exif_parts = []
                if 'Make' in fields_updated and args.make:
                    exif_parts.append(args.make)
                if 'Model' in fields_updated and args.model:
                    exif_parts.append(args.model)
                actions.append(f"EXIF: {' / '.join(exif_parts)}")

        # Apply Finder tags
        if finder_tags:
            success, tags_added = apply_finder_tags(file_path, finder_tags, dry_run=dry_run)
            if not success:
                continue

            if tags_added:
                actions.append(f"Tags: {', '.join(tags_added)}")

        dry_run_suffix = " (DRY RUN)" if dry_run else ""
        if actions:
            print(f"📌 Tagged: {filename} ({'; '.join(actions)}){dry_run_suffix}")
        else:
            print(f"✓ {filename}: Already tagged correctly{dry_run_suffix}")

        success_count += 1

    if success_count < len(file_paths):
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
