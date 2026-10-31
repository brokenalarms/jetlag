#!/usr/bin/env python3
"""
Report what a source holds, as one JSON line on stdout.

    --count               {"media_files": 12}
    --timestamped-names   {"has_timestamped_names": true}

The date check stops at the first dated filename, since a source can be a whole drive.
"""

import argparse
import json
import sys
from pathlib import Path

from lib.filesystem import find_media_files, iter_media_files
from lib.timestamp_source import parse_filename_timestamp


def has_timestamped_names(path: Path, extensions: list[str]) -> bool:
    return any(parse_filename_timestamp(str(f))[0] for f in iter_media_files(str(path), extensions))


def main() -> int:
    parser = argparse.ArgumentParser(description="Report a source's media count or filename dates")
    parser.add_argument("path", help="Folder to scan")
    parser.add_argument("--extensions", nargs="+", required=True, help="Media extensions to look for")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--count", action="store_true", help="Report the number of media files")
    mode.add_argument("--timestamped-names", action="store_true",
                      help="Report whether any filename carries a parseable date")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"ERROR: {path} does not exist", file=sys.stderr)
        return 1

    extensions = [e if e.startswith(".") else f".{e}" for e in args.extensions]
    if args.count:
        print(json.dumps({"media_files": len(find_media_files(str(path), extensions))}))
    else:
        print(json.dumps({"has_timestamped_names": has_timestamped_names(path, extensions)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
