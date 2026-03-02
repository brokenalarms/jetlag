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
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from lib.results import emit_result


SCRIPT_DIR = Path(__file__).parent


@dataclass
class GyroflowResult:
    gyroflow_path: str
    action: str  # "generated" | "skipped" | "would_generate"
    error: Optional[str] = None  # populated on error, None on success


def signal_handler(sig, frame):
    print("\n\nInterrupted by user", file=sys.stderr)
    sys.exit(130)


def has_motion_data(file_path: Path) -> Optional[bool]:
    """Check if video file contains motion/gyro data streams using ffprobe.

    Returns:
        True if motion data found, False if checked and none found,
        None if ffprobe is unavailable (cannot determine).
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_streams", str(file_path)
            ],
            capture_output=True, text=True
        )
    except OSError:
        return None
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
        sys.exit(1)

    with open(profiles_file) as f:
        data = yaml.safe_load(f)

    config = data.get("gyroflow")
    if not config:
        print("ERROR: No 'gyroflow' section found in media-profiles.yaml", file=sys.stderr)
        print("Add a 'gyroflow' section with at minimum a 'binary' path", file=sys.stderr)
        sys.exit(1)

    if not config.get("binary"):
        print("ERROR: No 'binary' path in gyroflow config in media-profiles.yaml", file=sys.stderr)
        sys.exit(1)

    return config


def generate_gyroflow_project(
    file_path: Path,
    apply: bool,
    binary: Optional[str] = None,
    preset_json: Optional[str] = None,
) -> GyroflowResult:
    """Generate a .gyroflow project file for a video.

    Args:
        file_path: Resolved path to the video file
        apply: Whether to actually generate (False = dry run)
        binary: Path to gyroflow CLI binary (required when apply=True)
        preset_json: JSON preset string for stabilization settings

    Returns:
        GyroflowResult with path, action, and optional error
    """
    gyroflow_path = str(file_path.with_suffix(".gyroflow"))

    if Path(gyroflow_path).exists():
        print(f"Already exists: {gyroflow_path}", file=sys.stderr)
        return GyroflowResult(gyroflow_path=gyroflow_path, action="skipped")

    motion_check = has_motion_data(file_path)
    if motion_check is None:
        print(f"Skipped: {gyroflow_path} (ffprobe not available)", file=sys.stderr)
        return GyroflowResult(gyroflow_path=gyroflow_path, action="skipped",
                              error="ffprobe not available — cannot check for motion data")
    if not motion_check:
        print(f"Skipped: {gyroflow_path} (no motion data)", file=sys.stderr)
        return GyroflowResult(gyroflow_path=gyroflow_path, action="skipped")

    if not apply:
        print(f"Would generate: {gyroflow_path}", file=sys.stderr)
        return GyroflowResult(gyroflow_path=gyroflow_path, action="would_generate")

    if not binary or not os.path.isfile(binary):
        # Configured path missing — try PATH (e.g. Homebrew install)
        path_binary = shutil.which("gyroflow")
        if path_binary:
            binary = path_binary
        else:
            configured = binary or "(not set)"
            print(f"Warning: Gyroflow not found at configured path ({configured}) or in $PATH", file=sys.stderr)
            print("Install Gyroflow or update the 'binary' path in media-profiles.yaml", file=sys.stderr)
            return GyroflowResult(
                gyroflow_path=gyroflow_path,
                action="skipped",
                error=f"Gyroflow not found at {configured} or in $PATH",
            )

    cmd = [binary, str(file_path), "--export-project", "2"]

    if preset_json and preset_json != "{}":
        cmd.extend(["--preset", preset_json])

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        error_msg = result.stderr.rstrip() if result.stderr else f"exit code {result.returncode}"
        print(error_msg, file=sys.stderr)
        return GyroflowResult(gyroflow_path=gyroflow_path, action="skipped", error=error_msg)

    if not Path(gyroflow_path).exists():
        error_msg = f"No project file created for {gyroflow_path}"
        print(f"Gyroflow ran but {error_msg}", file=sys.stderr)
        return GyroflowResult(gyroflow_path=gyroflow_path, action="skipped", error=error_msg)

    print(f"Generated: {gyroflow_path}", file=sys.stderr)
    return GyroflowResult(gyroflow_path=gyroflow_path, action="generated")


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

    # Config and binary are only needed when applying
    binary = None
    preset_json = args.preset
    if args.apply:
        config = load_gyroflow_config()
        binary = config["binary"]
        if not preset_json:
            preset_json = json.dumps(config.get("preset", {}))

    result = generate_gyroflow_project(file_path, args.apply, binary, preset_json)
    emit_result(result)


if __name__ == "__main__":
    main()
