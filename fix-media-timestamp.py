#!/usr/bin/env python3
"""
Media timestamp fixing script - Python implementation
Declaratively fixes photo and video metadata timestamps
Ensures file system timestamps match EXIF data for both photos and videos
"""

import argparse
import os
import re
import signal
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Callable

# Handle Ctrl-C gracefully
def signal_handler(sig, frame):
    print("\n\nInterrupted by user", file=sys.stderr)
    sys.exit(130)

signal.signal(signal.SIGINT, signal_handler)

try:
    import humanize
except ImportError:
    print("Error: humanize library not found. Install with: pip install humanize", file=sys.stderr)
    sys.exit(1)

# Global cache for exiftool data to avoid reading same file multiple times
_exif_cache: Dict[str, Dict[str, str]] = {}

def same_as_original(dt_with_tz: datetime) -> str:
    """Keep same as DateTimeOriginal with timezone"""
    return dt_with_tz.strftime('%Y:%m:%d %H:%M:%S%z')

def utc_from_date(dt_with_tz: datetime) -> str:
    """Convert datetime with timezone to UTC (no timezone suffix)"""
    return dt_with_tz.astimezone(timezone.utc).strftime('%Y:%m:%d %H:%M:%S')

def remove_field(dt_with_tz: datetime) -> None:
    """Mark field for removal"""
    return None

def same_local_time_current_tz(dt_with_tz: datetime) -> str:
    """Keep same local time as DateTimeOriginal for FCP compatibility"""
    # File system timestamps can't store timezone, so just use the local time
    # FCP will interpret this as local time in whatever timezone it's running
    return dt_with_tz.strftime('%Y:%m:%d %H:%M:%S')

# File system timestamp functions - these are the only timestamps we modify
def to_utc(datetime_str: str) -> str:
    """Convert local time with timezone to UTC (equivalent to bash to_utc function)"""
    try:
        dt = datetime.strptime(datetime_str, '%Y:%m:%d %H:%M:%S%z')
        return dt.astimezone(timezone.utc).strftime('%Y:%m:%d %H:%M:%S')
    except ValueError:
        return ""

def get_timezone_for_country(input_country: str, date_str: Optional[str] = None) -> Optional[str]:
    """Get timezone for country using CSV lookup (lines 536-604 from bash)"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    timezone_dir = os.path.join(script_dir, "lib", "timezones")
    country_csv = os.path.join(timezone_dir, "country.csv")
    timezone_csv = os.path.join(timezone_dir, "time_zone.csv")

    # Check if CSV files exist
    if not os.path.exists(country_csv) or not os.path.exists(timezone_csv):
        return None

    # Step 1: Resolve input to country code
    country_code = ""
    if len(input_country) == 2:
        # Input is likely a country code
        country_code = input_country.upper()
    else:
        # Input is country name, find the code
        try:
            with open(country_csv, 'r') as f:
                for line in f:
                    if line.strip() and input_country.lower() in line.lower():
                        country_code = line.split(',')[0].strip()
                        break
        except:
            return None

    if not country_code:
        return None

    # Step 2: Find appropriate timezone for country code and date
    try:
        with open(timezone_csv, 'r') as f:
            timezone_line = ""
            for line in f:
                if f",{country_code}," in line:
                    timezone_line = line.strip()

            if not timezone_line:
                return None

            # Step 3: Extract offset
            parts = timezone_line.split(',')
            if len(parts) >= 6:
                offset_seconds = int(parts[5])

                # Convert seconds to +HHMM format
                if offset_seconds == 0:
                    return "+0000"
                else:
                    abs_seconds = abs(offset_seconds)
                    hours = abs_seconds // 3600
                    minutes = (abs_seconds % 3600) // 60
                    sign = "+" if offset_seconds >= 0 else "-"
                    return f"{sign}{hours:02d}:{minutes:02d}"
    except:
        pass

    return None

def get_country_name(input_country: str) -> str:
    """Get full country name for display"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    country_csv = os.path.join(script_dir, "lib", "timezones", "country.csv")

    if len(input_country) == 2:
        try:
            with open(country_csv, 'r') as f:
                for line in f:
                    if line.startswith(input_country.upper() + ","):
                        return line.split(',', 1)[1].strip().strip('"')
        except:
            pass

    return input_country

def get_expected_file_system_time(datetime_original: datetime) -> str:
    """Get the expected file system timestamp (displays original shooting time)

    IMPORTANT: This intentionally creates "wrong" file timestamps for browsing convenience.

    Philosophy:
    - EXIF metadata (DateTimeOriginal, CreationDate) stores the TRUE shooting time with timezone
      Example: 13:39:34+08:00 (shot in Taiwan) - this is the source of truth, never changes

    - File system timestamps (birth/modify date) are set to ALWAYS display the shooting time
      Example: Shot at 13:39 in Taiwan → file ALWAYS shows 13:39
      Example: Whether you're in Japan (+09:00) or Taiwan (+08:00), file shows 13:39

    Why: This allows browsing files chronologically as they happened during the day.
         When editing footage from a trip, you can see "morning at 9am, lunch at 1pm" etc.
         regardless of what timezone you're currently in.

    Trade-off: The file timestamp will NOT represent the correct UTC moment.
               - File shows: 13:39+09:00 (when in Japan) = 04:39 UTC ❌ (wrong!)
               - Real UTC: 05:39 UTC (from 13:39+08:00)
               - But for browsing/editing purposes, seeing 13:39 is more useful than seeing 14:39

    The EXIF metadata always has the correct UTC/timezone, so no information is lost.

    Implementation:
    - Extract wall-clock time from source timezone (13:39:34 from 13:39:34+08:00)
    - touch/SetFile will interpret this as current system timezone
    - Result: file displays 13:39 regardless of where you are viewing it
    """
    # Extract the wall-clock time from the shooting timezone
    # Example: 13:39:34+08:00 → "13:39:34"
    # This will be interpreted by touch/SetFile as current system timezone
    return datetime_original.strftime('%Y:%m:%d %H:%M:%S')

# FileModifyDate and FileAccessDate are file system timestamps, not EXIF metadata
# They will be handled separately by set_file_system_timestamps()

def read_exif_data(file_path: str) -> Dict[str, str]:
    """Read all relevant EXIF data with single exiftool call (cached)"""
    # Check cache first
    if file_path in _exif_cache:
        return _exif_cache[file_path]

    fields = [
        "DateTimeOriginal", "CreateDate", "ModifyDate", "CreationDate",
        "QuickTime:MediaCreateDate", "QuickTime:MediaModifyDate", "Keys:CreationDate"
    ]

    cmd = ["exiftool", "-s"] + [f"-{field}" for field in fields] + [file_path]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        # Parse exiftool output
        data = {}
        for line in result.stdout.strip().split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()
                # Normalize QuickTime field names for consistency
                if key == "MediaCreateDate":
                    data["MediaCreateDate"] = value
                elif key == "MediaModifyDate":
                    data["MediaModifyDate"] = value
                else:
                    data[key] = value

        # Cache the result
        _exif_cache[file_path] = data
        return data
    except subprocess.CalledProcessError as e:
        print(f"Error reading EXIF data: {e}", file=sys.stderr)
        return {}

def is_valid_timestamp(timestamp_str: str) -> bool:
    """Check if timestamp is valid (not null/zero date)"""
    if not timestamp_str:
        return False
    # Reject null timestamps like 0000:00:00 00:00:00
    if timestamp_str.startswith("0000:00:00"):
        return False
    return True

def parse_datetime_original(datetime_str: str) -> Optional[datetime]:
    """Parse DateTimeOriginal string to datetime object with timezone"""
    if not datetime_str:
        return None
        
    # Handle format: "2025:05:14 16:38:07+02:00"
    pattern = r'^(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})([\+\-]\d{2}):?(\d{2})$'
    match = re.match(pattern, datetime_str)
    
    if match:
        year, month, day, hour, minute, second, tz_hour, tz_min = match.groups()
        
        # Create timezone-aware datetime
        dt_str = f"{year}-{month}-{day} {hour}:{minute}:{second}"
        tz_str = f"{tz_hour}:{tz_min}" if ':' not in f"{tz_hour}{tz_min}" else f"{tz_hour}{tz_min}"
        
        try:
            dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
            # Parse timezone offset
            tz_sign = 1 if tz_hour.startswith('+') else -1
            tz_hours = int(tz_hour[1:])
            tz_minutes = int(tz_min)
            tz_offset = tz_sign * (tz_hours * 60 + tz_minutes)

            # Create timezone-aware datetime
            tz = timezone(timedelta(minutes=tz_offset))
            return dt.replace(tzinfo=tz)
        except ValueError:
            return None
    
    return None

def ensure_colon_tz(tz_str: str) -> str:
    """Ensure timezone has colon format (+0200 -> +02:00, +02:00 stays +02:00)"""
    return re.sub(r'([+-][0-9]{2}):?([0-9]{2})$', r'\1:\2', tz_str)

def normalize_timezone_format(value: str) -> str:
    """Normalize timezone format for consistent comparison"""
    if not value:
        return ""

    # Normalize timezone format: +02:00 <-> +0200 (remove colon for comparison)
    return re.sub(r'([+-]\d{2}):(\d{2})$', r'\1\2', value)

def normalize_exif_value(value: str) -> str:
    """Normalize EXIF value for comparison (handle timezone format differences)"""
    if not value:
        return ""

    # Normalize timezone format for comparison
    return normalize_timezone_format(value)

def parse_filename_timestamp(file_path: str) -> Optional[str]:
    """Parse timestamp from filename patterns (comprehensive set from bash lib-timestamp.sh)"""
    base = os.path.basename(file_path)

    # VID_YYYYMMDD_HHMMSS, IMG_YYYYMMDD_HHMMSS, LRV_YYYYMMDD_HHMMSS (Insta360)
    match = re.match(r'^(VID|LRV|IMG)_([0-9]{8})_([0-9]{6})', base)
    if match:
        d, t = match.groups()[1], match.groups()[2]
        return f"{d[:4]}:{d[4:6]}:{d[6:8]} {t[:2]}:{t[2:4]}:{t[4:6]}"

    # DJI_YYYYMMDDHHMMSS_* (DJI Mavic 3 and newer)
    match = re.match(r'DJI_([0-9]{4})([0-9]{2})([0-9]{2})([0-9]{6})_', base)
    if match:
        year, month, day, time = match.groups()
        d = f"{year}{month}{day}"
        t = time
        return f"{d[:4]}:{d[4:6]}:{d[6:8]} {t[:2]}:{t[2:4]}:{t[4:6]}"

    # DSC_YYYYMMDD_HHMMSS (Sony cameras)
    match = re.match(r'DSC_([0-9]{4})([0-9]{2})([0-9]{2})_', base)
    if match:
        year, month, day = match.groups()
        d = f"{year}{month}{day}"
        return f"{d[:4]}:{d[4:6]}:{d[6:8]} 00:00:00"  # No time in pattern, use 00:00:00

    # Screenshot YYYY-MM-DD at HH.MM.SS (macOS screenshots)
    match = re.match(r'Screenshot\s+([0-9]{4})-([0-9]{2})-([0-9]{2})\s+at\s+([0-9]{1,2})\.([0-9]{2})\.([0-9]{2})', base)
    if match:
        year, month, day, hour, minute, second = match.groups()
        return f"{year}:{month}:{day} {hour.zfill(2)}:{minute}:{second}"

    # Generic YYYYMMDD anywhere in filename
    match = re.search(r'([0-9]{4})([0-9]{2})([0-9]{2})', base)
    if match:
        year, month, day = match.groups()
        # Validation: year 2000-2099, month 01-12, day 01-31
        if (2000 <= int(year) <= 2099 and 1 <= int(month) <= 12 and 1 <= int(day) <= 31):
            return f"{year}:{month}:{day} 00:00:00"

    return None

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

def file_timestamps_need_update(file_path: str, datetime_original: datetime) -> bool:
    """Check if file system timestamps need updating"""
    current_fs = get_file_system_timestamps(file_path)
    expected_time = datetime_original.strftime('%Y:%m:%d %H:%M:%S')
    
    # Check if either birth time or modify time differs from expected
    return (current_fs.get("birth", "") != expected_time or 
            current_fs.get("modify", "") != expected_time)

def determine_changes(file_path: str, datetime_original: datetime) -> Dict[str, Optional[str]]:
    """Determine what changes are needed by comparing current vs expected values"""
    current_data = read_exif_data(file_path)
    changes = {}
    
    for field, transform_func in FIELD_TRANSFORMS.items():
        expected = transform_func(datetime_original)
        current = current_data.get(field, "")
        
        # Normalize both for comparison
        current_norm = normalize_exif_value(current)
        expected_norm = normalize_exif_value(expected) if expected else ""
        
        if current_norm != expected_norm:
            changes[field] = expected
    
    return changes

def apply_exif_changes(file_path: str, changes: Dict[str, Optional[str]]) -> bool:
    """Apply EXIF changes with single exiftool call"""
    if not changes:
        return True

    cmd = ["exiftool", "-P", "-fast2", "-overwrite_original"]
    
    for field, value in changes.items():
        if value is None:
            # Remove field
            cmd.append(f"-{field}=")
        else:
            # Set field
            cmd.append(f"-{field}={value}")
    
    cmd.append(file_path)
    
    try:
        subprocess.run(cmd, capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error applying EXIF changes: {e}", file=sys.stderr)
        return False

def write_datetime_original(file_path: str, datetime_with_tz: str) -> bool:
    """Write DateTimeOriginal to file if missing"""
    try:
        cmd = ["exiftool", "-P", "-overwrite_original", f"-DateTimeOriginal={datetime_with_tz}", file_path]
        subprocess.run(cmd, capture_output=True, check=True)
        # Invalidate cache since file was modified
        if file_path in _exif_cache:
            del _exif_cache[file_path]
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error writing DateTimeOriginal: {e}", file=sys.stderr)
        return False

def write_quicktime_createdate(file_path: str, datetime_original: datetime) -> bool:
    """Write QuickTime CreateDate as UTC

    This heals corrupted QuickTime CreateDate fields (common in iPhone files).
    Writes the UTC equivalent of the shooting time to QuickTime CreateDate.

    Args:
        file_path: Path to the media file
        datetime_original: datetime object with timezone info

    Returns:
        True if successful, False otherwise
    """
    try:
        # Convert to UTC
        # Example: 2025:07:17 12:49:38+08:00 → 2025:07:17 04:49:38 UTC
        utc_dt = datetime_original.astimezone(timezone.utc)
        utc_time = utc_dt.strftime("%Y:%m:%d %H:%M:%S")

        # Write UTC directly to QuickTime fields (no timezone conversion needed)
        # QuickTime spec says these should be UTC, so write UTC directly
        cmd = [
            "exiftool",
            "-P",
            "-overwrite_original",
            f"-QuickTime:CreateDate={utc_time}",
            f"-QuickTime:MediaCreateDate={utc_time}",
            file_path
        ]
        subprocess.run(cmd, capture_output=True, check=True)

        # Invalidate cache since file was modified
        if file_path in _exif_cache:
            del _exif_cache[file_path]
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error writing QuickTime CreateDate: {e}", file=sys.stderr)
        return False

def set_file_system_timestamps(file_path: str, expected_timestamp: str) -> bool:
    """Set file system timestamps using pre-computed value"""
    # Expected timestamp is already in the correct local time format: YYYY:MM:DD HH:MM:SS
    try:
        # Parse the expected timestamp
        dt = datetime.strptime(expected_timestamp, '%Y:%m:%d %H:%M:%S')

        # For SetFile (MM/DD/YYYY HH:MM:SS)
        setfile_time = dt.strftime('%m/%d/%Y %H:%M:%S')

        # For touch (YYYYMMDDHHMM.SS)
        touch_time = dt.strftime('%Y%m%d%H%M.%S')

        # Apply file system timestamp changes
        subprocess.run(["SetFile", "-d", setfile_time, file_path],
                      capture_output=True, check=True)
        subprocess.run(["touch", "-t", touch_time, file_path],
                      capture_output=True, check=True)

        return True
    except subprocess.CalledProcessError as e:
        print(f"Error setting file system timestamps: {e}", file=sys.stderr)
        return False

def get_best_timestamp(file_path: str, timezone_offset: Optional[str] = None, overwrite_datetimeoriginal: bool = False) -> tuple[Optional[str], str]:
    """Get the best timestamp using 5-tier priority system from bash lib-timestamp.sh
    Returns: (timestamp_string, source_description)
    """
    exif_data = read_exif_data(file_path)
    file_timestamps = get_file_system_timestamps(file_path)
    base = os.path.basename(file_path)

    if overwrite_datetimeoriginal:
        filename_timestamp = parse_filename_timestamp(file_path)
        if filename_timestamp and re.match(r'^(VID|LRV|IMG)_[0-9]{8}_[0-9]{6}', base):
            return filename_timestamp, "filename"

    # Priority 1: DateTimeOriginal with timezone (authoritative source)
    datetime_original = exif_data.get("DateTimeOriginal", "")
    if datetime_original and re.search(r'[+-]\d{2}:?\d{2}$', datetime_original):
        # Has timezone, extract just the datetime part
        timestamp = re.sub(r'([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}).*', r'\1', datetime_original)
        return timestamp, "DateTimeOriginal with timezone"

    # Priority 2: CreationDate with timezone (iPhone videos)
    creation_date = exif_data.get("CreationDate", "")
    if creation_date and re.search(r'[+-]\d{2}:?\d{2}$', creation_date):
        # Has timezone, extract just the datetime part
        timestamp = re.sub(r'([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}).*', r'\1', creation_date)
        return timestamp, "CreationDate with timezone"

    # Priority 2.5: Keys:CreationDate with Z marker (iPhone UTC that needs timezone)
    # This is for iPhone files where QuickTime CreateDate is corrupted but Keys:CreationDate has correct UTC
    if creation_date and creation_date.endswith('Z') and timezone_offset:
        # Parse UTC time (remove Z suffix)
        timestamp = creation_date[:-1].strip()
        if re.match(r'[0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}', timestamp):
            return timestamp, "CreationDate with Z (UTC)"

    # Priority 3: Filename for VID/IMG/LRV files with parseable names (Insta360, etc.)
    filename_timestamp = parse_filename_timestamp(file_path)
    if filename_timestamp and re.match(r'^(VID|LRV|IMG)_[0-9]{8}_[0-9]{6}', base):
        return filename_timestamp, "filename"

    # Priority 4: DateTimeOriginal without timezone
    if datetime_original and re.search(r'[0-9]', datetime_original):
        timestamp = re.sub(r'([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}).*', r'\1', datetime_original)
        return timestamp, "DateTimeOriginal"

    # Priority 5: MediaCreateDate (usually UTC)
    media_create_date = exif_data.get("MediaCreateDate", "")
    if media_create_date and re.search(r'[0-9]', media_create_date):
        timestamp = re.sub(r'([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}).*', r'\1', media_create_date)
        if is_valid_timestamp(timestamp):
            return timestamp, "MediaCreateDate"

    # Priority 6: File timestamps
    if file_timestamps.get("birth"):
        return file_timestamps["birth"], "file birthtime"
    elif file_timestamps.get("modify"):
        return file_timestamps["modify"], "file mtime"

    return None, "no timestamps found"

def get_all_timestamp_data(file_path: str, timezone_offset: Optional[str] = None, overwrite_datetimeoriginal: bool = False) -> dict:
    """Get all current timestamp data from file"""
    data = {
        "file_path": file_path,  # Store file path for filename parsing
        "exif": read_exif_data(file_path),
        "file_system": get_file_system_timestamps(file_path),
        "datetime_original_str": "",
        "datetime_original": None,
        "timestamp_source": "",
        "timezone_source": ""  # Track where timezone came from
    }

    # Use 5-tier priority system to find best timestamp
    best_timestamp, source = get_best_timestamp(file_path, timezone_offset, overwrite_datetimeoriginal)
    data["timestamp_source"] = source

    if best_timestamp:
        if source == "CreationDate with timezone":
            # Use existing CreationDate with timezone
            data["datetime_original_str"] = data["exif"].get("CreationDate", "")
            data["timezone_source"] = "Keys:CreationDate metadata"
            if data["datetime_original_str"]:
                data["datetime_original"] = parse_datetime_original(data["datetime_original_str"])
        elif source in ["DateTimeOriginal with timezone", "DateTimeOriginal"]:
            # Use existing DateTimeOriginal
            data["datetime_original_str"] = data["exif"].get("DateTimeOriginal", "")
            data["timezone_source"] = "DateTimeOriginal metadata"
            if data["datetime_original_str"]:
                data["datetime_original"] = parse_datetime_original(data["datetime_original_str"])
        elif source == "CreationDate with Z (UTC)":
            # Keys:CreationDate has UTC with Z marker, convert to local time using timezone_offset
            # This handles iPhone files where QuickTime CreateDate is corrupted
            if timezone_offset:
                utc_dt = datetime.strptime(best_timestamp, "%Y:%m:%d %H:%M:%S").replace(tzinfo=timezone.utc)
                # Parse timezone offset
                tz_match = re.match(r'([+-])(\d{2}):?(\d{2})', timezone_offset)
                if tz_match:
                    sign, hours, minutes = tz_match.groups()
                    offset_seconds = int(hours) * 3600 + int(minutes) * 60
                    if sign == '-':
                        offset_seconds = -offset_seconds
                    local_tz = timezone(timedelta(seconds=offset_seconds))
                    local_dt = utc_dt.astimezone(local_tz)
                    datetime_with_tz = local_dt.strftime("%Y:%m:%d %H:%M:%S") + timezone_offset
                    data["datetime_original_str"] = datetime_with_tz
                    data["datetime_original"] = parse_datetime_original(datetime_with_tz)
                    data["timezone_source"] = f"--timezone flag ({timezone_offset})"
        elif source == "MediaCreateDate":
            # MediaCreateDate is in UTC, need timezone to convert to local time
            if timezone_offset:
                # Convert UTC timestamp to local time with timezone
                utc_dt = datetime.strptime(best_timestamp, "%Y:%m:%d %H:%M:%S").replace(tzinfo=timezone.utc)
                # Parse timezone offset
                tz_match = re.match(r'([+-])(\d{2}):?(\d{2})', timezone_offset)
                if tz_match:
                    sign, hours, minutes = tz_match.groups()
                    offset_seconds = int(hours) * 3600 + int(minutes) * 60
                    if sign == '-':
                        offset_seconds = -offset_seconds
                    local_tz = timezone(timedelta(seconds=offset_seconds))
                    local_dt = utc_dt.astimezone(local_tz)
                    datetime_with_tz = local_dt.strftime("%Y:%m:%d %H:%M:%S") + timezone_offset
                    data["datetime_original_str"] = datetime_with_tz
                    data["datetime_original"] = parse_datetime_original(datetime_with_tz)
                    data["timezone_source"] = f"--timezone flag ({timezone_offset})"
        else:
            # For filename or file timestamps, need timezone to create proper timestamp
            if timezone_offset:
                datetime_with_tz = f"{best_timestamp}{timezone_offset}"
                data["datetime_original_str"] = datetime_with_tz
                data["datetime_original"] = parse_datetime_original(datetime_with_tz)
                data["timezone_source"] = f"--timezone flag ({timezone_offset})"

    return data

def check_file_system_timestamps_need_update(file_path: str, datetime_original: datetime) -> bool:
    """Check if file system timestamps need updating to match original shooting time"""
    current_fs = get_file_system_timestamps(file_path)
    expected_time = get_expected_file_system_time(datetime_original)

    # Parse expected timestamp
    try:
        expected_dt = datetime.strptime(expected_time, '%Y:%m:%d %H:%M:%S')
    except ValueError:
        return True  # Can't parse expected time, assume update needed

    # Check modify time (this is the primary timestamp we care about)
    # Birth time is nice to have but not all filesystems support it reliably
    modify_needs_update = True
    if current_fs.get("modify"):
        try:
            current_modify = datetime.strptime(current_fs["modify"], '%Y:%m:%d %H:%M:%S')
            diff = abs((current_modify - expected_dt).total_seconds())
            # Allow 1 second tolerance for filesystem timing
            modify_needs_update = diff > 1
        except ValueError:
            modify_needs_update = True  # Can't parse, assume update needed

    # Also check birth time if it exists
    birth_needs_update = False
    if current_fs.get("birth"):
        try:
            current_birth = datetime.strptime(current_fs["birth"], '%Y:%m:%d %H:%M:%S')
            diff = abs((current_birth - expected_dt).total_seconds())
            # Allow 1 second tolerance for filesystem timing
            birth_needs_update = diff > 1
        except ValueError:
            birth_needs_update = True  # Can't parse, assume update needed

    # Only require update if modify time needs it (birth time is optional)
    return modify_needs_update or birth_needs_update

def check_quicktime_createdate_needs_update(file_path: str, datetime_original: datetime) -> bool:
    """Check if QuickTime CreateDate needs updating to match correct UTC"""
    exif_data = read_exif_data(file_path)
    # Check MediaCreateDate as that's what we're actually writing
    current_create_date = exif_data.get("MediaCreateDate", "")

    if not current_create_date:
        return False  # Not a QuickTime file, skip this check

    # Expected UTC from the datetime_original
    expected_utc = datetime_original.astimezone(timezone.utc).strftime("%Y:%m:%d %H:%M:%S")

    # Check if they match (allow 1 second tolerance for rounding)
    try:
        current_dt = datetime.strptime(current_create_date, "%Y:%m:%d %H:%M:%S")
        expected_dt = datetime.strptime(expected_utc, "%Y:%m:%d %H:%M:%S")
        diff = abs((current_dt - expected_dt).total_seconds())
        return diff > 1
    except ValueError:
        # Can't parse, assume needs update
        return True

def determine_needed_changes(file_path: str, datetime_original: datetime) -> dict:
    """Determine what changes are needed"""
    changes = {
        "file_timestamps": False,
        "quicktime_createdate": False
    }

    # Check if file system timestamps need updating
    changes["file_timestamps"] = check_file_system_timestamps_need_update(file_path, datetime_original)

    # Check if QuickTime CreateDate needs updating
    changes["quicktime_createdate"] = check_quicktime_createdate_needs_update(file_path, datetime_original)

    return changes

def format_exif_timestamp_display(ts: str) -> str:
    """Format EXIF timestamp with dashes for date, colons for time"""
    # Convert YYYY:MM:DD HH:MM:SS to YYYY-MM-DD HH:MM:SS
    return ts.replace(':', '-', 2) if ts else ts

def format_original_timestamps(current_data: dict) -> str:
    """Format original timestamp display from raw data"""
    parts = []

    # Show the timestamp source that was actually used
    source = current_data.get("timestamp_source", "")

    if source == "DateTimeOriginal with timezone":
        datetime_original = current_data["exif"].get("DateTimeOriginal", "")
        if datetime_original:
            parts.append(f"{format_exif_timestamp_display(datetime_original)} (DateTimeOriginal)")
    elif source == "CreationDate with timezone":
        creation_date = current_data["exif"].get("CreationDate", "")
        if creation_date:
            parts.append(f"{format_exif_timestamp_display(creation_date)} (Keys:CreationDate)")
    elif source == "CreationDate with Z (UTC)":
        creation_date = current_data["exif"].get("CreationDate", "")
        if creation_date:
            parts.append(f"{format_exif_timestamp_display(creation_date)} (Keys:CreationDate UTC)")
    elif source == "DateTimeOriginal":
        datetime_original = current_data["exif"].get("DateTimeOriginal", "")
        if datetime_original:
            parts.append(f"{format_exif_timestamp_display(datetime_original)} (DateTimeOriginal)")
    elif source == "MediaCreateDate":
        media_create = current_data["exif"].get("MediaCreateDate", "")
        file_ts = current_data["file_system"].get("modify", "")
        if media_create:
            parts.append(f"{format_exif_timestamp_display(media_create)} UTC (MediaCreateDate)")
        if file_ts:
            parts.append(f"{format_exif_timestamp_display(file_ts)} local (file)")
    elif source == "filename":
        # Show the parsed filename timestamp
        filename_ts = parse_filename_timestamp(current_data.get("file_path", ""))
        if filename_ts:
            parts.append(f"{format_exif_timestamp_display(filename_ts)} (from filename)")
        else:
            parts.append(f"(from filename)")
    elif source in ["file birthtime", "file mtime"]:
        file_ts = current_data["file_system"].get("modify", "")
        if file_ts:
            parts.append(f"{format_exif_timestamp_display(file_ts)} (file)")

    return ", ".join(parts) if parts else "(no timestamps available)"

def format_timestamp_display(dt: datetime) -> str:
    """Format timestamp with dashes for date, colons for time"""
    return dt.strftime('%Y-%m-%d %H:%M:%S%z')

def format_corrected_timestamp(datetime_original: datetime, timestamp_source: str, timezone_source: str) -> str:
    """Format corrected timestamp display"""
    corrected_str = format_timestamp_display(datetime_original)
    tz_value = datetime_original.strftime('%z')
    # Format timezone with colon
    tz_formatted = f"{tz_value[:3]}:{tz_value[3:]}" if len(tz_value) == 5 else tz_value

    # Determine source display based on actual timestamp source
    if "CreationDate" in timestamp_source:
        source_display = "Keys:CreationDate"
    elif "DateTimeOriginal" in timestamp_source:
        source_display = "DateTimeOriginal"
    else:
        source_display = timestamp_source

    # Use the actual timezone source
    tz_source_display = timezone_source if timezone_source else f"{source_display} metadata ({tz_formatted})"
    if not timezone_source.startswith("--timezone"):
        tz_source_display = f"{timezone_source} ({tz_formatted})"

    return f"{corrected_str} (from {source_display} with timezone, tz: {tz_source_display})"

def format_time_delta(seconds: float) -> str:
    """Format time delta in human-readable format"""
    sign = "+" if seconds > 0 else "-"
    td = timedelta(seconds=abs(seconds))
    return f"{sign}{humanize.naturaldelta(td)}"

def format_change_description(changes: dict, delta_seconds: Optional[float] = None, current_data: dict = None) -> str:
    """Format change description from changes data"""
    parts = []

    # Check if DateTimeOriginal needs to be written
    needs_datetime_original = current_data and not current_data.get("exif", {}).get("DateTimeOriginal")
    if needs_datetime_original:
        parts.append("DateTimeOriginal (missing)")

    if changes.get("file_timestamps"):
        if delta_seconds is not None and abs(delta_seconds) > 1:
            delta_str = format_time_delta(delta_seconds)
            parts.append(f"File timestamps ({delta_str})")
        else:
            parts.append("File timestamps")

    if changes.get("quicktime_createdate"):
        # Show what the current MediaCreateDate is
        if current_data:
            media_create = current_data.get("exif", {}).get("MediaCreateDate", "")
            if media_create:
                parts.append(f"QuickTime CreateDate (was: {format_exif_timestamp_display(media_create)} UTC)")
            else:
                parts.append(f"QuickTime CreateDate (missing)")
        else:
            parts.append("QuickTime CreateDate")

    return ", ".join(parts) if parts else "No change"

def fix_media_timestamps(file_path: str, dry_run: bool = False, verbose: bool = False, timezone_offset: Optional[str] = None, overwrite_datetimeoriginal: bool = False) -> bool:
    """Main function to fix media (photo/video) timestamps

    Args:
        file_path: Path to media file
        dry_run: If True, show changes without applying them
        verbose: Show verbose output
        timezone_offset: Timezone offset (e.g. +09:00) for files missing timezone
        overwrite_datetimeoriginal: If True, overwrite DateTimeOriginal even if it exists (for genuinely wrong timestamps)
    """

    # Get all data
    current_data = get_all_timestamp_data(file_path, timezone_offset, overwrite_datetimeoriginal)
    
    # Display header
    filename = os.path.basename(file_path)
    print(f"\033[36m🔍 {filename}\033[0m")
    
    if not current_data["datetime_original"]:
        # Check if we have CreateDate but missing timezone
        create_date = current_data["exif"].get("CreateDate", "")
        if create_date and not timezone_offset:
            print("❌ File has CreateDate but no DateTimeOriginal")
            print(f"   CreateDate: {create_date}")
            print("   Use --timezone to specify timezone (e.g., --timezone +09:00)")
            return False
        print("❌ No valid DateTimeOriginal found")
        return False
    
    datetime_original = current_data["datetime_original"]
    changes = determine_needed_changes(file_path, datetime_original)
    
    # Format and display timestamps
    original_display = format_original_timestamps(current_data)
    print(f"📅 Original : {original_display}")

    timestamp_source = current_data.get("timestamp_source", "")
    timezone_source = current_data.get("timezone_source", "")
    corrected_display = format_corrected_timestamp(datetime_original, timestamp_source, timezone_source)
    print(f"⏱️ Corrected: {corrected_display}")
    
    utc_dt = datetime_original.astimezone(timezone.utc)
    utc_display = utc_dt.strftime('%Y-%m-%d %H:%M:%S UTC')
    print(f"🌐 UTC      : {utc_display}")

    # Calculate delta if file timestamps need updating
    delta_seconds = None
    if changes.get("file_timestamps"):
        current_fs = current_data["file_system"]
        if current_fs.get("modify"):
            try:
                # Parse current file timestamp (no timezone, local time)
                current_dt = datetime.strptime(current_fs["modify"], '%Y:%m:%d %H:%M:%S')
                # Parse expected timestamp (no timezone, local time)
                expected_time = get_expected_file_system_time(datetime_original)
                expected_dt = datetime.strptime(expected_time, '%Y:%m:%d %H:%M:%S')
                # Calculate delta
                delta_seconds = (expected_dt - current_dt).total_seconds()
            except:
                pass

    # Display changes
    change_desc = format_change_description(changes, delta_seconds, current_data)
    has_changes = changes["file_timestamps"] or changes.get("quicktime_createdate", False)

    if dry_run and has_changes:
        print(f"📊 Change   : {change_desc} (DRY RUN)")
        return True
    else:
        print(f"📊 Change   : {change_desc}")

    if not has_changes:
        return True

    if dry_run:
        return True

    # Apply changes
    success = True

    # Write DateTimeOriginal if:
    # 1. It's missing and we have timezone info, OR
    # 2. overwrite_datetimeoriginal flag is set (for genuinely wrong timestamps)
    should_write_datetime_original = (
        (not current_data["exif"].get("DateTimeOriginal") and current_data["datetime_original_str"]) or
        (overwrite_datetimeoriginal and current_data["datetime_original_str"])
    )

    if should_write_datetime_original:
        if overwrite_datetimeoriginal and current_data["exif"].get("DateTimeOriginal"):
            print("   ⚠️  Overwriting existing DateTimeOriginal (--overwrite-datetimeoriginal flag)")
        if not write_datetime_original(file_path, current_data["datetime_original_str"]):
            print("   ❌ Failed to write DateTimeOriginal")
            success = False

    # Heal QuickTime CreateDate if needed
    if changes.get("quicktime_createdate"):
        if not write_quicktime_createdate(file_path, datetime_original):
            print("   ❌ Failed to heal QuickTime CreateDate")
            success = False

    # Update file system timestamps if needed
    if changes["file_timestamps"]:
        expected_file_timestamp = get_expected_file_system_time(datetime_original)
        if not set_file_system_timestamps(file_path, expected_file_timestamp):
            print("   ❌ Failed to apply file timestamps")
            success = False

    return success

def main():
    """Command line interface"""
    parser = argparse.ArgumentParser(description='Fix media timestamps - ensures file system timestamps match EXIF data')
    parser.add_argument('file', help='Media file (photo or video) to process')
    parser.add_argument('--timezone', help='Timezone offset (e.g. +09:00) - required when DateTimeOriginal lacks timezone info')
    parser.add_argument('--country', help='Country code or name for automatic timezone lookup (e.g. JP, Taiwan)')
    parser.add_argument('--apply', action='store_true', help='Apply changes (default: dry run)')
    parser.add_argument('--overwrite-datetimeoriginal', action='store_true', help='Overwrite DateTimeOriginal even if it exists (for genuinely wrong timestamps)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')

    args = parser.parse_args()

    # Convert file path to absolute path to ensure exiftool can find it
    file_path = os.path.abspath(args.file)

    # Handle country lookup for timezone
    timezone_offset = args.timezone
    if args.country and not timezone_offset:
        timezone_offset = get_timezone_for_country(args.country)
        if timezone_offset:
            print(f"→ Country: {get_country_name(args.country)} (timezone: {timezone_offset})")
        else:
            print(f"Error: Could not determine timezone for country '{args.country}'", file=sys.stderr)
            return 1

    success = fix_media_timestamps(
        file_path,
        dry_run=not args.apply,
        verbose=args.verbose,
        timezone_offset=timezone_offset,
        overwrite_datetimeoriginal=args.overwrite_datetimeoriginal
    )

    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())