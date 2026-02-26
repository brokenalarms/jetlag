#!/usr/bin/env python3
"""
batch-generate-gyroflow.py
Batch generates .gyroflow project files for all video files in a directory.

Usage: batch-generate-gyroflow.py [DIR] [--extensions .mp4 .mov] [--preset '...'] [--apply]

Scans DIR (default: current directory) for video files and runs
generate-gyroflow.py on each one. All other arguments are passed through.
"""

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib.filesystem import find_media_files, parse_machine_output

SCRIPT_DIR = Path(__file__).parent


def signal_handler(sig, frame):
    print("\n\nInterrupted by user", file=sys.stderr)
    sys.exit(130)


def main():
    signal.signal(signal.SIGINT, signal_handler)

    parser = argparse.ArgumentParser(
        description="Batch generate .gyroflow project files for video files in a directory."
    )
    parser.add_argument("directory", nargs="?", default=".",
                        help="Directory to scan (default: current directory)")
    parser.add_argument("--extensions", nargs="+", default=[".mp4", ".mov"],
                        help="File extensions to process (default: .mp4 .mov)")
    parser.add_argument("--preset", help="JSON preset string for stabilization settings")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default: dry run)")

    args = parser.parse_args()

    source_dir = Path(args.directory).resolve()
    if not source_dir.is_dir():
        print(f"ERROR: Directory not found: {source_dir}", file=sys.stderr)
        sys.exit(1)

    files = find_media_files(str(source_dir), args.extensions)

    if not files:
        print(f"No video files found in {source_dir}", file=sys.stderr)
        sys.exit(0)

    print(f"Found {len(files)} video file(s) to process", file=sys.stderr)
    print(file=sys.stderr)

    stats = {"processed": 0, "generated": 0, "skipped": 0, "failed": 0}

    for i, file_path in enumerate(files, 1):
        stats["processed"] += 1
        print(f"[{i}/{len(files)}] ./{os.path.relpath(file_path)}", file=sys.stderr)

        cmd = [sys.executable, str(SCRIPT_DIR / "generate-gyroflow.py"), str(file_path)]

        if args.preset:
            cmd.extend(["--preset", args.preset])
        if args.apply:
            cmd.append("--apply")

        result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)

        if result.returncode != 0:
            stats["failed"] += 1
            continue

        data = parse_machine_output(result.stdout)
        action = data.get("action", "")

        if action == "generated":
            stats["generated"] += 1
        else:
            stats["skipped"] += 1

    print(file=sys.stderr)
    print("===========================================", file=sys.stderr)
    print("GYROFLOW BATCH SUMMARY", file=sys.stderr)
    print("-------------------------------------------", file=sys.stderr)
    print(f"Total files: {stats['processed']}", file=sys.stderr)
    print(f"Generated: {stats['generated']}", file=sys.stderr)
    print(f"Skipped: {stats['skipped']}", file=sys.stderr)
    if stats["failed"] > 0:
        print(f"Failed: {stats['failed']}", file=sys.stderr)

    if not args.apply:
        print("DRY RUN — use --apply to generate project files", file=sys.stderr)


if __name__ == "__main__":
    main()
