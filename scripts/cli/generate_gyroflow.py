#!/usr/bin/env python3
"""
generate-gyroflow.sh
Generates a .gyroflow project file for a video with gyroscope data.

Usage: generate-gyroflow.sh FILE --preset '{"stabilization": {...}}' [--apply]

Command line for lib/generate_gyroflow.py; prints the result as @@key=value lines.
"""

import argparse
import json
import sys
from pathlib import Path

from lib.command_line import install_interrupt_handlers
from lib.generate_gyroflow import generate_gyroflow_project
from lib.profiles import ProfilesFileMissing, load_config
from cli.results import emit_result


def load_gyroflow_config() -> dict:
    """The profiles file's gyroflow section, or exit saying where to add it."""
    try:
        config = load_config().get("gyroflow")
    except ProfilesFileMissing as missing:
        print(f"ERROR: Config file not found: {missing.path}", file=sys.stderr)
        print("Add a 'gyroflow' section to media-profiles.yaml", file=sys.stderr)
        sys.exit(1)
    if not config:
        print("ERROR: No 'gyroflow' section found in media-profiles.yaml", file=sys.stderr)
        print("Add a 'gyroflow' section to media-profiles.yaml", file=sys.stderr)
        sys.exit(1)
    return config


def main():
    install_interrupt_handlers()

    parser = argparse.ArgumentParser(
        prog="generate-gyroflow.sh",
        description="Generate a .gyroflow project file for a video with gyroscope data."
    )
    parser.add_argument("file", help="Video file to process")
    parser.add_argument("--preset", help="JSON preset string for stabilization settings")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default: dry run)")

    args = parser.parse_args()

    file_path = Path(args.file).resolve()
    if not file_path.exists():
        print(f"ERROR: File not found: {file_path}", file=sys.stderr)
        print(f"@@error=File not found: {file_path}")
        sys.exit(1)

    # Config and binary are only needed when applying
    binary = None
    preset_json = args.preset
    if args.apply:
        config = load_gyroflow_config()
        binary = config.get("binary")
        if not preset_json:
            preset_json = json.dumps(config.get("preset", {}))

    result = generate_gyroflow_project(file_path, args.apply, binary, preset_json)
    emit_result(result)


if __name__ == "__main__":
    main()
