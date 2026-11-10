#!/usr/bin/env python3
"""
Fix one photo or video file's timestamps.

Command line for lib/fix_timestamp.py: parses arguments, resolves the timezone,
runs the correction and prints its result as @@key=value lines.
"""

import argparse
import os
import signal
import sys

from lib.cli import attach_negative_option_values
from lib.countries import get_country_name, get_timezone_for_country
from lib.fix_timestamp import fix_media_timestamps
from lib.results import emit_result
from lib.timestamp_source import is_zone_name, normalize_timezone_input


# Handle Ctrl-C gracefully
def signal_handler(sig, frame):
    print("\n\nInterrupted by user", file=sys.stderr)
    sys.exit(130)


def main():
    """Command line interface"""
    signal.signal(signal.SIGINT, signal_handler)
    parser = argparse.ArgumentParser(description='Fix media timestamps - ensures file system timestamps match EXIF data')
    parser.add_argument('file', help='Media file (photo or video) to process')
    parser.add_argument('--timezone', help='Timezone offset (e.g. +09:00) - always required for this step (or pass --country to resolve one)')
    parser.add_argument('--country', help='Country code or name for automatic timezone lookup (e.g. JP, Taiwan)')
    parser.add_argument('--apply', action='store_true', help='Apply changes (default: dry run)')
    parser.add_argument('--infer-from-filename', action='store_true', help='Use filename timestamp as source of truth (requires --timezone)')
    parser.add_argument('--time-offset', type=int, default=None, help='Seconds to add/subtract from resolved timestamp (requires --timezone)')
    parser.add_argument('--preserve-wallclock-time', action='store_true', help='Preserve literal wall-clock shooting time (10:30 stays 10:30) instead of converting to current timezone for display')
    parser.add_argument('--force-timezone', action='store_true', help='Confirm relabelling a file whose metadata already carries a timezone; without it such files are refused')

    args = parser.parse_args(attach_negative_option_values(sys.argv[1:]))

    # Convert file path to absolute path to ensure exiftool can find it
    file_path = os.path.abspath(args.file)

    # Handle country lookup for timezone
    timezone_spec = args.timezone
    if timezone_spec and not is_zone_name(timezone_spec):
        # Normalize timezone format (add + sign if missing, ensure colon)
        timezone_spec = normalize_timezone_input(timezone_spec)

    if args.country and not timezone_spec:
        timezone_spec = get_timezone_for_country(args.country)
        if timezone_spec:
            print(f"→ Country: {get_country_name(args.country)} (timezone: {timezone_spec})", file=sys.stderr)
        else:
            print(f"Error: Could not determine timezone for country '{args.country}'", file=sys.stderr)
            return 1

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
        dry_run=not args.apply,
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