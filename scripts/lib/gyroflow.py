"""Generate a .gyroflow project file for a video with gyroscope data.

The project file is placed next to the video by the Gyroflow CLI and used by the
Gyroflow Toolbox plugin for real-time stabilization.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from lib.exiftool import exiftool


@dataclass
class GyroflowResult:
    gyroflow_path: str
    action: str  # "generated" | "skipped" | "would_generate"
    error: Optional[str] = None  # populated on error, None on success


MOTION_TRACK_KEYWORDS = ("motion", "gyro", "imu", "rtmd", "camm", "gpmd")


def has_motion_data(file_path: Path) -> Optional[bool]:
    """Check if a video carries a motion/gyro metadata track (Sony rtmd, GoPro gpmd, camm).

    ExifTool reads each track's handler and metadata format from the file's
    header, so the media itself is never scanned. Every track is reported
    (``-a``): a GoPro file carries several metadata tracks, and the gyro one
    need not be the one a single value would show.

    Returns:
        True if motion data found, False if checked and none found,
        None if exiftool is unavailable (cannot determine).
    """
    try:
        tracks = exiftool.read_tags(
            str(file_path), ["HandlerDescription", "MetaFormat"], extra_args=["-a", "-G4"]
        )
    except FileNotFoundError:
        return None
    if "error" in tracks:
        return None
    return any(
        keyword in value.lower()
        for value in tracks.values()
        for keyword in MOTION_TRACK_KEYWORDS
    )


def gyroflow_search_locations() -> tuple[Path, Path]:
    """The two directories that may hold a Gyroflow.app, in resolution order.

    Overridable via JETLAG_APPLICATIONS_DIR / JETLAG_TOOLS_DIR so the app and
    the tests can point resolution at somewhere other than the real machine.
    """
    applications = Path(os.environ.get("JETLAG_APPLICATIONS_DIR", "/Applications"))
    tools = Path(
        os.environ.get("JETLAG_TOOLS_DIR")
        or Path.home() / "Library" / "Application Support" / "Jetlag" / "tools"
    )
    return applications, tools


def gyroflow_app_binary(containing_dir: Path) -> Optional[str]:
    """The CLI inside a Gyroflow.app under containing_dir, if it is runnable.

    Gyroflow ships as a full .app: the CLI only works from inside the bundle,
    where its code signature is valid and the mdk/Qt frameworks it links
    against are on hand.
    """
    binary = containing_dir / "Gyroflow.app" / "Contents" / "MacOS" / "gyroflow"
    if binary.is_file() and os.access(binary, os.X_OK):
        return str(binary)
    return None


def resolve_gyroflow_binary(configured_path: Optional[str] = None) -> Optional[str]:
    """Find the gyroflow CLI: /Applications -> Jetlag tools dir -> PATH -> configured.

    Returns the resolved path, or None if not found anywhere.
    """
    for containing_dir in gyroflow_search_locations():
        found = gyroflow_app_binary(containing_dir)
        if found:
            return found

    path_binary = shutil.which("gyroflow")
    if path_binary:
        return path_binary

    if configured_path and os.path.isfile(configured_path):
        return configured_path

    return None


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
        print(f"Skipped: {gyroflow_path} (exiftool not available)", file=sys.stderr)
        return GyroflowResult(gyroflow_path=gyroflow_path, action="skipped",
                              error="exiftool not available — cannot check for motion data")
    if not motion_check:
        print(f"Skipped: {gyroflow_path} (no motion data)", file=sys.stderr)
        return GyroflowResult(gyroflow_path=gyroflow_path, action="skipped")

    if not apply:
        print(f"Would generate: {gyroflow_path}", file=sys.stderr)
        return GyroflowResult(gyroflow_path=gyroflow_path, action="would_generate")

    resolved = resolve_gyroflow_binary(binary)
    if not resolved:
        configured = binary or "(not set)"
        print(f"Warning: Gyroflow not found — checked /Applications, the Jetlag tools directory, $PATH, and the configured path ({configured})", file=sys.stderr)
        print("Run scripts/tools/download-gyroflow.sh or install Gyroflow", file=sys.stderr)
        return GyroflowResult(
            gyroflow_path=gyroflow_path,
            action="skipped",
            error=f"Gyroflow not found at {configured} or in $PATH",
        )
    binary = resolved

    cmd = [binary, str(file_path), "--export-project", "2"]

    if preset_json and preset_json != "{}":
        cmd.extend(["--preset", preset_json])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as e:
        # A binary that cannot be executed here — built for another platform, or not an
        # executable at all — is as unusable as a missing one, so skip rather than crash.
        error_msg = f"Gyroflow not found: cannot execute {binary} ({e.strerror})"
        print(f"Warning: {error_msg}", file=sys.stderr)
        return GyroflowResult(gyroflow_path=gyroflow_path, action="skipped", error=error_msg)

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
