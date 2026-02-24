"""
macOS file-system timestamp operations.

Reads and writes file birth time using macOS-specific tools (stat -f, SetFile).
These functions only work on macOS and should be conditionally imported.
"""

import subprocess
from datetime import datetime
from typing import Dict


def get_file_system_timestamps(file_path: str) -> Dict[str, str]:
    """Get file system timestamps (birth time and modification time)"""
    try:
        # Get birth time (creation time)
        birth_result = subprocess.run(
            ["stat", "-f", "%SB", "-t", "%Y:%m:%d %H:%M:%S", file_path],
            capture_output=True, text=True, check=True
        )
        birth_time = birth_result.stdout.strip()

        # Get modification time
        mod_result = subprocess.run(
            ["date", "-r", file_path, "+%Y:%m:%d %H:%M:%S"],
            capture_output=True, text=True, check=True
        )
        mod_time = mod_result.stdout.strip()

        return {"birth": birth_time, "modify": mod_time}
    except subprocess.CalledProcessError:
        return {"birth": "", "modify": ""}


def set_file_system_timestamps(file_path: str, timestamp_str: str) -> bool:
    """Set file system birth time

    Note: Only sets birth time, not modification time. Modification time naturally
    reflects when the file was last modified (e.g., by exiftool metadata writes).

    Args:
        file_path: Path to the file
        timestamp_str: Timestamp in format "YYYY:MM:DD HH:MM:SS"

    Returns:
        True if successful, False otherwise
    """
    try:
        # Parse the timestamp
        dt = datetime.strptime(timestamp_str, '%Y:%m:%d %H:%M:%S')

        # Set birth time using SetFile (macOS-specific, requires Xcode Command Line Tools)
        # Format: "MM/DD/YYYY HH:MM:SS"
        setfile_format = dt.strftime('%m/%d/%Y %H:%M:%S')
        subprocess.run(
            ["SetFile", "-d", setfile_format, file_path],
            check=True,
            capture_output=True
        )

        return True
    except (subprocess.CalledProcessError, ValueError) as e:
        import sys
        print(f"Error setting file timestamps: {e}", file=sys.stderr)
        return False


def get_expected_file_system_time(datetime_original: datetime, preserve_wallclock: bool = False) -> str:
    """Calculate what file system timestamp should be

    Default: Convert to current timezone for consistent display
    Example: Shot at 10:29 in +08:00, viewing in +09:00 -> file timestamp should be 11:29

    With preserve_wallclock: Use shooting time directly
    Example: Shot at 10:29 -> file timestamp should be 10:29

    Args:
        datetime_original: datetime object with timezone info
        preserve_wallclock: If True, preserve wall-clock shooting time

    Returns:
        Timestamp string in format "YYYY:MM:DD HH:MM:SS"
    """
    if preserve_wallclock:
        # Use shooting time directly (wall-clock time)
        return datetime_original.strftime('%Y:%m:%d %H:%M:%S')
    else:
        # Convert to current local timezone for consistent display
        # This ensures file timestamp matches what Keys:CreationDate displays
        local_dt = datetime_original.astimezone()
        return local_dt.strftime('%Y:%m:%d %H:%M:%S')


def check_file_system_timestamps_need_update(file_path: str, datetime_original: datetime, preserve_wallclock: bool = False) -> bool:
    """Check if file system birth time needs updating

    Note: Only checks birth time. Modification time naturally changes when files are
    modified (e.g., by exiftool) and shouldn't be artificially set.

    Args:
        file_path: Path to the media file
        datetime_original: datetime object with timezone info
        preserve_wallclock: If True, match wall-clock shooting time instead

    Returns:
        True if birth time needs updating, False otherwise
    """
    current_fs = get_file_system_timestamps(file_path)
    expected_time = get_expected_file_system_time(datetime_original, preserve_wallclock)

    # Parse expected timestamp
    try:
        expected_dt = datetime.strptime(expected_time, '%Y:%m:%d %H:%M:%S')
    except ValueError:
        return True  # Can't parse expected time, assume update needed

    # Check birth time (essential for video editor import)
    if current_fs.get("birth"):
        try:
            current_birth = datetime.strptime(current_fs["birth"], '%Y:%m:%d %H:%M:%S')
            diff = abs((current_birth - expected_dt).total_seconds())
            # Allow 60 second tolerance - matches bash version behavior
            # Small differences from file copies or system timing shouldn't trigger updates
            return diff > 60
        except ValueError:
            return True  # Can't parse, assume update needed

    # Birth time missing or invalid
    return True
