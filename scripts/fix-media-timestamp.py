#!/usr/bin/env python3
"""
Fix one photo or video file's timestamps.

Command line for lib/fix_timestamp.py: parses arguments, resolves the timezone,
runs the correction and prints its result as @@key=value lines.
"""

import argparse
import os
import sys

from lib.cli import (
    UnknownLocation,
    UnknownTimezone,
    add_timezone_args,
    attach_negative_option_values,
    install_interrupt_handlers,
    resolve_timezone,
)
from lib.countries import get_country_name
from lib.fix_timestamp import fix_media_timestamps
from lib.results import emit_result


def main():
    """Command line interface"""
    install_interrupt_handlers()
    parser = argparse.ArgumentParser(description='Fix media timestamps - ensures file system timestamps match EXIF data')
    parser.add_argument('file', help='Media file (photo or video) to process')
    add_timezone_args(parser, '--country')
    parser.add_argument('--apply', action='store_true', help='Apply changes (default: dry run)')
    parser.add_argument('--infer-from-filename', action='store_true', help='Use filename timestamp as source of truth (requires --timezone)')
    parser.add_argument('--time-offset', type=int, default=None, help='Seconds to add/subtract from resolved timestamp (requires --timezone)')
    parser.add_argument('--preserve-wallclock-time', action='store_true', help='Preserve literal wall-clock shooting time (10:30 stays 10:30) instead of converting to current timezone for display')
    parser.add_argument('--force-timezone', action='store_true', help='Confirm relabelling a file whose metadata already carries a timezone; without it such files are refused')

    args = parser.parse_args(attach_negative_option_values(sys.argv[1:]))

    # Convert file path to absolute path to ensure exiftool can find it
    file_path = os.path.abspath(args.file)

    try:
        timezone_spec = resolve_timezone(args.timezone, args.location)
    except UnknownTimezone:
        print(f"Error: unknown timezone '{args.timezone}' — use an IANA zone name "
              "(e.g., Pacific/Auckland) or a +HH:MM offset", file=sys.stderr)
        return 1
    except UnknownLocation:
        print(f"Error: Could not determine timezone for country '{args.location}'", file=sys.stderr)
        return 1
    if timezone_spec and not args.timezone:
        print(f"→ Country: {get_country_name(args.location)} (timezone: {timezone_spec})", file=sys.stderr)

    if args.infer_from_filename and not timezone_spec:
        print("Error: --infer-from-filename requires --timezone", file=sys.stderr)
        return 1

    if args.time_offset is not None and not timezone_spec:
        print("Error: --time-offset requires --timezone", file=sys.stderr)
        return 1

    if not timezone_spec:
        print("Error: --timezone is required (or --country to resolve one)", file=sys.stderr)
        return 1

    result = fix_media_timestamps(
        file_path,
        apply=args.apply,
        timezone_spec=timezone_spec,
        infer_from_filename=args.infer_from_filename,
        preserve_wallclock=args.preserve_wallclock_time,
        time_offset_seconds=args.time_offset,
        force_timezone=args.force_timezone,
    )

    emit_result(result)

    return 0 if result.timestamp_action != "error" else 1


if __name__ == "__main__":
    sys.exit(main())
