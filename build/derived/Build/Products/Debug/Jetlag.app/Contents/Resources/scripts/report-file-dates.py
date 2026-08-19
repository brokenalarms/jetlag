#!/usr/bin/env python3
"""
Pre-flight scanner — report timestamp sources for files in a directory.

Calls read_timestamp_sources() on each file and emits machine-readable
@@key=value lines summarising parseability and a sample preview.

Usage:
    report-file-dates.py <source-dir> --file-extensions .mp4 .mov
"""

import argparse
import os
import sys
from pathlib import Path

from lib.filesystem import find_media_files
from lib.timestamp_source import read_timestamp_sources


def main():
    parser = argparse.ArgumentParser(description="Report timestamp sources for media files")
    parser.add_argument("source_dir", help="Directory to scan")
    parser.add_argument(
        "--file-extensions",
        nargs="+",
        default=[".mp4", ".mov", ".jpg", ".jpeg", ".png", ".insv"],
        help="File extensions to scan (default: .mp4 .mov .jpg .jpeg .png .insv)",
    )

    args = parser.parse_args()

    source_dir = os.path.abspath(args.source_dir)
    if not os.path.isdir(source_dir):
        print(f"Error: {source_dir} is not a directory", file=sys.stderr)
        return 1

    files = find_media_files(source_dir, args.file_extensions)
    total = len(files)

    if total == 0:
        print("@@total_count=0")
        print("@@parseable_count=0")
        print("@@all_parseable=true")
        return 0

    parseable_count = 0
    sample_report = None

    for f in files:
        report = read_timestamp_sources(str(f))
        if report.filename_parseable:
            parseable_count += 1
        if sample_report is None:
            sample_report = (f, report)

    all_parseable = parseable_count == total

    print(f"@@total_count={total}")
    print(f"@@parseable_count={parseable_count}")
    print(f"@@all_parseable={'true' if all_parseable else 'false'}")

    if sample_report:
        sample_file, report = sample_report
        print(f"@@sample_file={sample_file.name}")
        if report.metadata_date:
            print(f"@@sample_metadata_date={report.metadata_date.strftime('%Y:%m:%d %H:%M:%S')}")
        if report.metadata_tz:
            print(f"@@sample_metadata_tz={report.metadata_tz}")
        if report.filename_date:
            print(f"@@sample_filename_date={report.filename_date.strftime('%Y:%m:%d %H:%M:%S')}")
        if report.filename_pattern:
            print(f"@@sample_filename_pattern={report.filename_pattern}")

    # Human-readable summary on stderr
    print(f"Scanned {total} files: {parseable_count} with parseable filenames", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
