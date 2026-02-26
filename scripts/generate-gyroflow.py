#!/usr/bin/env python3
"""
generate-gyroflow.py
Generates a .gyroflow project file for a video with gyroscope data.

Usage: generate-gyroflow.py FILE --preset '{"stabilization": {...}}' [--apply]

The .gyroflow project file is placed next to the video by Gyroflow CLI.
Used by the Gyroflow Toolbox plugin for real-time stabilization.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import yaml


SCRIPT_DIR = Path(__file__).parent


def signal_handler(sig, frame):
    print("\n\nInterrupted by user", file=sys.stderr)
    sys.exit(130)


def has_motion_data(file_path: Path) -> bool:
    """Check if video file contains motion/gyro data streams using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_streams", str(file_path)
            ],
            capture_output=True, text=True
        )
    except FileNotFoundError:
        print("ffprobe not found — skipping motion data check", file=sys.stderr)
        return False
    if result.returncode != 0:
        return False

    data = json.loads(result.stdout)
    for stream in data.get("streams", []):
        if stream.get("codec_type") not in ("data", "subtitle"):
            continue
        handler = stream.get("tags", {}).get("handler_name", "").lower()
        codec_tag = stream.get("codec_tag_string", "").lower()
        if any(kw in handler for kw in ["motion", "gyro", "imu", "rtmd", "camm"]):
            return True
        if any(kw in codec_tag for kw in ["gpmd", "camm", "rtmd"]):
            return True
    return False


def load_gyroflow_config() -> dict:
    """Load gyroflow config from media-profiles.yaml."""
    profiles_file = SCRIPT_DIR / "media-profiles.yaml"
    if not profiles_file.exists():
        print(f"ERROR: Config file not found: {profiles_file}", file=sys.stderr)
        print("Add a 'gyroflow' section to media-profiles.yaml with 'binary' path", file=sys.stderr)
        print(f"@@error=Config file not found: {profiles_file}")
        sys.exit(1)

    with open(profiles_file) as f:
        data = yaml.safe_load(f)

    config = data.get("gyroflow")
    if not config:
        print("ERROR: No 'gyroflow' section found in media-profiles.yaml", file=sys.stderr)
        print("Add a 'gyroflow' section with at minimum a 'binary' path", file=sys.stderr)
        print("@@error=No 'gyroflow' section in media-profiles.yaml")
        sys.exit(1)

    if not config.get("binary"):
        print("ERROR: No 'binary' path in gyroflow config in media-profiles.yaml", file=sys.stderr)
        print("@@error=No 'binary' path in gyroflow config")
        sys.exit(1)

    return config


def main():
    signal.signal(signal.SIGINT, signal_handler)

    parser = argparse.ArgumentParser(
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

    gyroflow_path = file_path.with_suffix(".gyroflow")
    rel_path = os.path.join(".", os.path.relpath(gyroflow_path))

    dry_run_suffix = " (DRY RUN)" if not args.apply else ""

    if gyroflow_path.exists():
        print(f"Already exists: {rel_path}{dry_run_suffix}", file=sys.stderr)
        print(f"@@gyroflow={gyroflow_path}")
        print(f"@@action=skipped")
        return

    if not has_motion_data(file_path):
        print(f"Skipped: {rel_path} (no motion data){dry_run_suffix}", file=sys.stderr)
        print(f"@@gyroflow={gyroflow_path}")
        print(f"@@action=skipped")
        return

    if not args.apply:
        print(f"Would generate: {rel_path} (DRY RUN)", file=sys.stderr)
        print(f"@@gyroflow={gyroflow_path}")
        print(f"@@action=skipped")
        return

    config = load_gyroflow_config()
    binary = config["binary"]

    if not os.path.isfile(binary):
        print(f"ERROR: Gyroflow binary not found at: {binary}", file=sys.stderr)
        print("Install Gyroflow or update the 'binary' path in media-profiles.yaml", file=sys.stderr)
        print(f"@@error=Gyroflow binary not found at: {binary}")
        sys.exit(1)

    preset_json = args.preset or json.dumps(config.get("preset", {}))

    cmd = [binary, str(file_path), "--export-project", "2"]

    if preset_json and preset_json != "{}":
        cmd.extend(["--preset", preset_json])

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        error_msg = result.stderr.rstrip() if result.stderr else f"exit code {result.returncode}"
        print(error_msg, file=sys.stderr)
        print(f"@@error={error_msg}")
        print(f"@@action=skipped")
        return

    if not gyroflow_path.exists():
        print(f"Gyroflow ran but no project file created for {rel_path}", file=sys.stderr)
        print(f"@@error=No project file created for {rel_path}")
        print(f"@@action=skipped")
        return

    print(f"Generated: {rel_path}", file=sys.stderr)
    print(f"@@gyroflow={gyroflow_path}")
    print(f"@@action=generated")


if __name__ == "__main__":
    main()
