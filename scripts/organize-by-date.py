#!/usr/bin/env python3
"""
organize-by-date.py
Organizes a single file into date-based directory structure.
Uses DateTimeOriginal first, filename date patterns, falls back to file timestamps.
"""

import argparse
import os
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from lib.exiftool import exiftool
from lib.results import emit_result


@dataclass
class OrganizeResult:
    dest: str
    action: str  # "copied" | "moved" | "skipped" | "overwrote" | "would_copy" | "would_move" | "would_overwrite"

MONTH_ABBREVS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def get_file_date_for_organization(file_path: str) -> Optional[str]:
    """Get date in YYYY-MM-DD format for file organization.

    Priority: DateTimeOriginal > filename patterns > file mtime
    """
    try:
        data = exiftool.read_tags(file_path, ["DateTimeOriginal"], extra_args=["-fast2"])
        dt_str = data.get("DateTimeOriginal", "")
        if dt_str:
            date_part = dt_str.split(' ')[0]
            return date_part.replace(':', '-')
    except Exception:
        pass

    # Try filename patterns
    base = os.path.basename(file_path)

    m = re.match(r'^(?:VID|LRV|IMG)_(\d{8})_(\d{6})', base)
    if m:
        d = m.group(1)
        return f'{d[:4]}-{d[4:6]}-{d[6:8]}'

    m = re.search(r'DJI_(\d{4})(\d{2})(\d{2})\d{6}_', base)
    if m:
        return f'{m.group(1)}-{m.group(2)}-{m.group(3)}'

    m = re.search(r'(\d{4})(\d{2})(\d{2})', base)
    if m:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 2000 <= year <= 2099 and 1 <= month <= 12 and 1 <= day <= 31:
            return f'{m.group(1)}-{m.group(2)}-{m.group(3)}'

    # Fallback: file mtime
    try:
        mtime = os.path.getmtime(file_path)
        return datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
    except OSError:
        return None


def expand_path_template(template: str, file_date: str) -> str:
    """Expand path template with date components.

    Template variables: {{YYYY}}, {{MM}}, {{MMM}}, {{DD}}, {{YYYY-MM-DD}}
    file_date: YYYY-MM-DD format
    """
    year = file_date[:4]
    month = file_date[5:7]
    day = file_date[8:10]
    month_abbr = MONTH_ABBREVS[int(month)]

    expanded = template
    expanded = expanded.replace('{{YYYY}}', year)
    expanded = expanded.replace('{{MM}}', month)
    expanded = expanded.replace('{{MMM}}', month_abbr)
    expanded = expanded.replace('{{DD}}', day)
    expanded = expanded.replace('{{YYYY-MM-DD}}', file_date)

    expanded = expanded.replace('//', '/')
    expanded = expanded.rstrip('/')

    return expanded


def _handle_existing_target(file_path, target_file, target_path, abs_target,
                            base, organized_path, copy_mode, overwrite, apply):
    """Handle case where target file already exists."""
    src_size = os.path.getsize(file_path)
    dst_size = os.path.getsize(target_file)

    if overwrite:
        action = "overwrite"
    elif src_size == dst_size:
        action = "skip"
    elif apply:
        print(f"\u26a0\ufe0f  File exists: {base}", file=sys.stderr)
        print(f"   Source: {src_size} bytes, Dest: {dst_size} bytes", file=sys.stderr)
        try:
            sys.stderr.write("   (o)verwrite / (s)kip? ")
            sys.stderr.flush()
            with open('/dev/tty') as tty:
                choice = tty.readline().strip()
            action = "overwrite" if choice.lower().startswith('o') else "skip"
        except (OSError, EOFError):
            action = "skip"
    else:
        action = "skip"

    if action == "overwrite":
        if apply:
            os.makedirs(target_path, exist_ok=True)
            if copy_mode:
                shutil.copy2(file_path, target_file)
                print(f"\u267b\ufe0f  Overwrote: {base} \u2192 {organized_path}/", file=sys.stderr)
                return OrganizeResult(dest=abs_target, action="overwrote")
            else:
                shutil.move(file_path, target_file)
                print(f"\u267b\ufe0f  Overwrote: {base} \u2192 {organized_path}/", file=sys.stderr)
                return OrganizeResult(dest=abs_target, action="overwrote")
        else:
            print(f"[DRY RUN] Would overwrite: {file_path} \u2192 {abs_target}", file=sys.stderr)
            return OrganizeResult(dest=abs_target, action="would_overwrite")

    # Skip
    size_mb = src_size / 1048576
    if src_size == dst_size:
        print(f"\u23ed\ufe0f  Skipped (identical, {size_mb:.1f} MB): {base}", file=sys.stderr)
    else:
        print(f"\u23ed\ufe0f  Skipped (user choice): {base}", file=sys.stderr)

    return OrganizeResult(dest=abs_target, action="skipped")


def process_file(file_path: str, target_dir: str, template: str,
                 copy_mode: bool, overwrite: bool, apply: bool,
                 verbose: bool) -> OrganizeResult:
    """Process a single file for organization.

    Returns:
        OrganizeResult with dest path and action taken
    """
    base = os.path.basename(file_path)

    if verbose:
        print(f"Processing: {file_path}", file=sys.stderr)

    file_date = get_file_date_for_organization(file_path)
    if not file_date:
        print(f"ERROR: Cannot determine date for {base}", file=sys.stderr)
        sys.exit(1)

    if verbose:
        print(f"  Date: {file_date}", file=sys.stderr)

    organized_path = expand_path_template(template, file_date)

    target_path = os.path.join(target_dir.rstrip('/'), organized_path.lstrip('/'))
    target_file = os.path.join(target_path, base)

    if os.path.isabs(target_file):
        abs_target = target_file
    else:
        abs_target = os.path.join(os.getcwd(), target_file.lstrip('./'))

    # Check if file is already in correct location
    file_realdir = os.path.dirname(os.path.realpath(file_path))
    try:
        target_realpath = os.path.realpath(target_path)
    except OSError:
        target_realpath = target_path

    if file_realdir == target_realpath:
        print(f"\u2713 Already organized: {base} ({organized_path})", file=sys.stderr)
        return OrganizeResult(dest=abs_target, action="skipped")

    if os.path.exists(target_file):
        return _handle_existing_target(
            file_path, target_file, target_path, abs_target, base,
            organized_path, copy_mode, overwrite, apply
        )

    if apply:
        os.makedirs(target_path, exist_ok=True)
        if copy_mode:
            shutil.copy2(file_path, target_file)
            print(f"\u2705 Copied: {file_path} \u2192 {abs_target}", file=sys.stderr)
            return OrganizeResult(dest=abs_target, action="copied")
        else:
            shutil.move(file_path, target_file)
            print(f"\u2705 Moved: {file_path} \u2192 {abs_target}", file=sys.stderr)
            return OrganizeResult(dest=abs_target, action="moved")
    else:
        if copy_mode:
            print(f"[DRY RUN] Would copy: {file_path} \u2192 {abs_target}", file=sys.stderr)
            return OrganizeResult(dest=abs_target, action="would_copy")
        else:
            print(f"[DRY RUN] Would move: {file_path} \u2192 {abs_target}", file=sys.stderr)
            return OrganizeResult(dest=abs_target, action="would_move")


def main():
    parser = argparse.ArgumentParser(
        description='Organize a single file into date-based directory structure'
    )
    parser.add_argument('file', help='File to organize')
    parser.add_argument('--target', required=True,
                        help='Target directory for organized files')
    parser.add_argument('--template',
                        default='{{YYYY}}/{{YYYY}}-{{MM}}-{{DD}}',
                        help='Path template (default: {{YYYY}}/{{YYYY}}-{{MM}}-{{DD}})')
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


if __name__ == "__main__":
    main()
