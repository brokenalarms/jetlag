#!/usr/bin/env python3
"""
media-pipeline.py
Orchestrates media processing: ingest from source, process, output to target.

Usage: media-pipeline.py --profile PROFILE [--group GROUP] [OPTIONS]
       media-pipeline.py --source DIR --target DIR [--group GROUP] [OPTIONS]

Command line for lib/pipeline.py, which runs
INGEST (always) → [tag] → [fix-timestamp] → OUTPUT (always) → [gyroflow] → [archive-source].
"""

from __future__ import annotations

import argparse
import signal
import sys

from lib.pipeline import SIGNAL_MESSAGES, WORKING_DIR_NAME, emit_event, run, signal_handler


def build_parser():
    """Build the argument parser for media-pipeline."""
    parser = argparse.ArgumentParser(
        description="Orchestrates video timestamp fixing and organization into date-based folders."
    )
    parser.add_argument("--profile", help="Profile from media-profiles.yaml")
    parser.add_argument("--source", help="Directory containing media files (default: current directory)")
    parser.add_argument("--target", help="Target directory for organized files")
    parser.add_argument("--extensions", nargs="+", help="File extensions to process (e.g. .mp4 .mov); overrides the profile's file_extensions")
    parser.add_argument("--location", help="Location name/code for timezone lookup")
    parser.add_argument("--timezone", help="IANA zone name (e.g., Pacific/Auckland), resolved per file so a run spanning a DST changeover gets the right offset either side, or a fixed offset in +HHMM format (e.g., +0800)")
    parser.add_argument("--group", help="Optional group folder name substituted for {{GROUP}} in the profile's folder_template, or inserted between year and date by default (e.g., 'Japan' → YYYY/Japan/YYYY-MM-DD)")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default: dry run)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed processing info")
    parser.add_argument(
        "--tasks", nargs="+",
        choices=["tag", "fix-timestamp", "gyroflow", "archive-source"],
        default=["tag", "fix-timestamp", "gyroflow"],
        help="Optional pipeline steps to run (default: tag, fix-timestamp, gyroflow). Ingest and output are always on."
    )
    parser.add_argument(
        "--source-action",
        choices=["archive", "delete"],
        default="archive",
        help="Action for source after processing (default: archive). Requires archive-source in --tasks."
    )
    parser.add_argument(
        "--archive-destination",
        help="Directory to move the archived source folder into (default: where the source already is)."
    )
    parser.add_argument(
        "--archived-name",
        help="Name for the archived source folder (default: '<source> - copied <YYYY-MM-DD>')."
    )
    parser.add_argument(
        "--copy-companion-files", action="store_true",
        help="Also copy companion files (matching profile companion_extensions) to target."
    )
    parser.add_argument(
        "--infer-from-filename", action="store_true",
        help="Use filename timestamp as source of truth instead of EXIF metadata. Requires --timezone."
    )
    parser.add_argument(
        "--time-offset", type=int, default=None,
        help="Seconds to add/subtract from source timestamp (for clock correction). Requires --timezone."
    )
    parser.add_argument(
        "--update-filename-dates", action="store_true",
        help="Rename files to reflect corrected timestamps after fix-timestamp."
    )
    parser.add_argument(
        "--force-timezone", action="store_true",
        help="Override existing timezone in DateTimeOriginal with --timezone. Without this flag, the pipeline stops when a provided-vs-embedded conflict is detected."
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Replace files already at the organize destination. Without this flag, a destination already holding a different file is left alone and reported as a conflict."
    )
    parser.add_argument(
        "--allow-camera-mismatch", action="store_true",
        help="Import files whose camera Make/Model differs from the profile's. Their camera fields are left as the camera wrote them. Without this flag, an apply stops when such files are found."
    )
    parser.add_argument(
        "--unlock-protected", action="store_true",
        help="Import source files that are protected (locked, e.g. by a camera's Protect). Their copies in the target come out unlocked; the source files keep their lock. Without this flag, an apply stops when protected files are found."
    )
    parser.add_argument(
        "--allow-mixed-timezones", action="store_true",
        help="Allow processing files with different embedded timezones in a single batch. Without this flag, the pipeline stops when mixed timezones are detected."
    )
    parser.add_argument("--tags", help="Comma-separated Finder tags (overrides profile tags)")
    parser.add_argument("--make", help="EXIF camera make (overrides profile exif.make)")
    parser.add_argument("--model", help="EXIF camera model (overrides profile exif.model)")
    parser.add_argument(
        "--gyroflow-preset",
        help='JSON string overriding gyroflow stabilization preset from config (e.g. \'{"stabilization": {"max_zoom": 110.0}}\')'
    )
    parser.add_argument(
        "--working-dir",
        default=None,
        help=f"Working directory for intermediate files (default: <target>/{WORKING_DIR_NAME})"
    )
    return parser


def main():
    """Main entry point."""
    for sig in SIGNAL_MESSAGES:
        signal.signal(sig, signal_handler)

    run(build_parser().parse_args())


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        emit_event("pipeline_error", message=str(e))
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
