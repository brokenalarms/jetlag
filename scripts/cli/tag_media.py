#!/usr/bin/env python3
"""
Tag media files with Finder tags and camera EXIF metadata.

Command line for lib/tagging.py; prints each file's result as @@key=value lines.
"""

import argparse
import os
import sys

from lib.cli import install_interrupt_handlers
from lib.exiftool import MetadataWriteRefused
from cli.results import emit_result
from lib.tagging import parse_tag_list, tag_media_file


def main():
    install_interrupt_handlers()
    parser = argparse.ArgumentParser(prog="tag-media.sh", description='Tag media files with Finder tags and camera EXIF')
    parser.add_argument('files', nargs='+', help='Media files to tag')
    parser.add_argument('--make', help='Camera make/manufacturer to add to EXIF')
    parser.add_argument('--model', help='Camera model to add to EXIF')
    parser.add_argument('--tags', help='Comma-separated Finder tags to apply')
    parser.add_argument('--apply', action='store_true', help='Apply changes (default: dry run)')

    args = parser.parse_args()

    # Convert file paths to absolute paths to ensure exiftool can find them
    file_paths = [os.path.abspath(f) for f in args.files]

    finder_tags = parse_tag_list(args.tags)

    success_count = 0
    for file_path in file_paths:
        try:
            result = tag_media_file(file_path, finder_tags, args.make, args.model, apply=args.apply)
        except MetadataWriteRefused as refusal:
            print(f"❌ exiftool could not write {os.path.basename(file_path)}: {refusal}", file=sys.stderr)
            continue
        if result is None:
            continue

        emit_result(result)

        success_count += 1

    if success_count < len(file_paths):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
