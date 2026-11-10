#!/usr/bin/env python3
"""
organize-by-date.py
Organizes a single file into date-based directory structure.

Command line for lib/organize.py; prints the result as @@key=value lines.
"""

import argparse
import os
import sys

from lib.cli import install_interrupt_handlers
from lib.organize import DEFAULT_FOLDER_TEMPLATE, process_file
from lib.results import emit_result


def main():
    install_interrupt_handlers()
    parser = argparse.ArgumentParser(
        description='Organize a single file into date-based directory structure'
    )
    parser.add_argument('file', help='File to organize')
    parser.add_argument('--target', required=True,
                        help='Target directory for organized files')
    parser.add_argument('--template',
                        help=f'Path template (default: {DEFAULT_FOLDER_TEMPLATE.replace("{{GROUP}}/", "")})')
    parser.add_argument('--copy', action='store_true',
                        help='Copy instead of move')
    parser.add_argument('--overwrite', action='store_true',
                        help='Overwrite existing files')
    parser.add_argument('--apply', action='store_true',
                        help='Apply changes (default: dry run)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show detailed processing info')

    args = parser.parse_args()

    if not os.path.isfile(args.file):
        print(f"ERROR: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    target_dir = os.path.expanduser(args.target)

    result = process_file(
        args.file, target_dir, args.template,
        copy_mode=args.copy, overwrite=args.overwrite,
        apply=args.apply, verbose=args.verbose
    )

    emit_result(result)

    if result.action == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()
