#!/usr/bin/env python3
"""
Tag media files with Finder tags and camera EXIF metadata
Extracted from import-media.py for reuse in media-pipeline
"""

import subprocess
import sys
import os
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple
import argparse

from lib.metadata import metadata
from lib.results import emit_result


@dataclass
class TagResult:
    file: str
    tags_added: list[str]
    exif_make: str
    exif_model: str
    action: str  # "tagged" | "already_correct"

# Handle Ctrl-C gracefully
def signal_handler(sig, frame):  # noqa: ARG001
    print("\n\nInterrupted by user", file=sys.stderr)
    sys.exit(130)

def get_existing_finder_tags(file_path: str) -> List[str]:
    """Get existing Finder tags from a file"""
    try:
        result = subprocess.run(["tag", '--list', '--no-name', file_path],
                              capture_output=True, check=True, text=True)
        output = result.stdout.strip()
        if not output:
            return []
        return [tag.strip() for tag in output.split(',') if tag.strip()]
    except (subprocess.CalledProcessError, OSError):
        return []

def apply_finder_tags(file_path: str, tags: List[str], dry_run: bool = False) -> Tuple[bool, List[str]]:
    """Apply Finder tags to a file using macOS tag command

    Returns:
        (success, tags_added): Success status and list of tags that were actually added
    """
    if not tags:
        return True, []

    try:
        existing_tags = get_existing_finder_tags(file_path)
        tags_to_add = [tag for tag in tags if tag not in existing_tags]

        if not tags_to_add:
            return True, []

        if not dry_run:
            subprocess.run(["tag", '--add', ','.join(tags_to_add), file_path],
                          capture_output=True, check=True)
        return True, tags_to_add
    except OSError:
        print("Warning: 'tag' command not available — Finder tags require macOS", file=sys.stderr)
        return False, []
    except subprocess.CalledProcessError as e:
        print(f"Warning: Failed to apply tags to {file_path}: {e}", file=sys.stderr)
        return False, []

def get_existing_exif_camera(file_path: str) -> dict:
    """Get existing Make and Model from EXIF data"""
    try:
        return metadata.read_tags(file_path, ["Make", "Model"])
    except Exception:
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
        existing = get_existing_exif_camera(file_path)

        fields_to_update = []
        tag_args = []

        if make and existing.get('Make') != make:
            tag_args.append(f'-Make={make}')
            fields_to_update.append('Make')

        if model and existing.get('Model') != model:
            tag_args.append(f'-Model={model}')
            fields_to_update.append('Model')

        if not fields_to_update:
            return True, []

        if not dry_run:
            metadata.write_tags(file_path, tag_args)
        return True, fields_to_update
    except Exception as e:
        print(f"Warning: Failed to add camera info to {file_path}: {e}", file=sys.stderr)
        return False, []

def tag_media_file(file_path: str, finder_tags: List[str], make: Optional[str], model: Optional[str], dry_run: bool) -> Optional[TagResult]:
    """Process a single file: apply tags and EXIF, return structured result.

    Returns:
        TagResult on success, None if file not found or processing failed
    """
    if not os.path.exists(file_path):
        print(f"Warning: File not found: {file_path}", file=sys.stderr)
        return None

    filename = os.path.basename(file_path)
    actions = []
    all_tags_added: list[str] = []
    exif_make = ""
    exif_model = ""

    # Apply camera EXIF (Make and Model)
    if make or model:
        success, fields_updated = add_camera_to_exif(file_path, make=make, model=model, dry_run=dry_run)
        if not success:
            return None

        if fields_updated:
            exif_parts = []
            if 'Make' in fields_updated and make:
                exif_parts.append(make)
                exif_make = make
            if 'Model' in fields_updated and model:
                exif_parts.append(model)
                exif_model = model
            actions.append(f"EXIF: {' / '.join(exif_parts)}")

    # Apply Finder tags (macOS only — skipped on other platforms)
    if finder_tags:
        success, tags_added = apply_finder_tags(file_path, finder_tags, dry_run=dry_run)

        if success and tags_added:
            all_tags_added = tags_added
            actions.append(f"Tags: {', '.join(tags_added)}")

    dry_run_suffix = " (DRY RUN)" if dry_run else ""
    tag_action = "tagged" if actions else "already_correct"

    if actions:
        verb = "would tag" if dry_run else "tagged"
        print(f"📌 {verb}: {filename} ({'; '.join(actions)}){dry_run_suffix}", file=sys.stderr)
    else:
        print(f"✓ already tagged: {filename}{dry_run_suffix}", file=sys.stderr)

    return TagResult(
        file=filename,
        tags_added=all_tags_added,
        exif_make=exif_make,
        exif_model=exif_model,
        action=tag_action,
    )


def main():
    signal.signal(signal.SIGINT, signal_handler)
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
        result = tag_media_file(file_path, finder_tags, args.make, args.model, dry_run)
        if result is None:
            continue

        emit_result(result)

        success_count += 1

    if success_count < len(file_paths):
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
