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
import sys
import time
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

from lib.exiftool import exiftool
from lib.timestamp_source import (
    read_exif_data,
    _exif_cache,
    is_valid_timestamp,
    parse_datetime_original,
    ensure_colon_tz,
    normalize_timezone_input,
    normalize_timezone_format,
    normalize_exif_value,
    parse_filename_timestamp,
    get_best_timestamp,
    extract_metadata_timezone,
    read_timestamp_sources,
    clear_exif_cache,
)

if sys.platform == "darwin":
    from lib.file_timestamps import (
        get_file_system_timestamps,
        set_file_system_timestamps,
        check_file_system_timestamps_need_update,
        get_expected_file_system_time,
    )

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
    """Keep same local time as DateTimeOriginal"""
    # File system timestamps can't store timezone, so just use the local time
    # Applications will interpret this as local time in whatever timezone they're running
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


def write_exif_fields(file_path: str, field_args: list) -> bool:
    """Write multiple EXIF fields in a single exiftool call."""
    try:
        result = exiftool.write_tags(file_path, field_args)
        if file_path in _exif_cache:
            del _exif_cache[file_path]
        return result
    except Exception as e:
        print(f"Error writing EXIF fields: {e}", file=sys.stderr)
        return False


def write_datetime_original(file_path: str, datetime_with_tz: str) -> bool:
    """Write DateTimeOriginal to file if missing"""
    try:
        result = exiftool.write_tags(file_path, [f"-DateTimeOriginal={datetime_with_tz}"])
        if file_path in _exif_cache:
            del _exif_cache[file_path]
        return result
    except Exception as e:
        print(f"Error writing DateTimeOriginal: {e}", file=sys.stderr)
        return False

def write_keys_creationdate(file_path: str, datetime_original: datetime) -> bool:
    """Write Keys:CreationDate with original timezone

    Always writes DateTimeOriginal with its original timezone to maintain correct absolute time.

    Args:
        file_path: Path to the media file
        datetime_original: datetime object with timezone info

    Returns:
        True if successful, False otherwise
    """
    try:
        keys_value = datetime_original.strftime('%Y:%m:%d %H:%M:%S%z')
        keys_value = re.sub(r'([+-]\d{2})(\d{2})$', r'\1:\2', keys_value)

        result = exiftool.write_tags(file_path, [f"-Keys:CreationDate={keys_value}"])
        if file_path in _exif_cache:
            del _exif_cache[file_path]
        return result
    except Exception as e:
        print(f"Error writing Keys:CreationDate: {e}", file=sys.stderr)
        return False

def write_quicktime_createdate(file_path: str, datetime_original: datetime) -> bool:
    """Write QuickTime CreateDate as UTC

    This heals corrupted QuickTime CreateDate fields (common in iPhone files).
    Writes UTC directly without QuickTimeUTC flag. The flag is only used for READING
    (to convert stored UTC to local time for verification).

    Args:
        file_path: Path to the media file
        datetime_original: datetime object with timezone info
        

    Returns:
        True if successful, False otherwise
    """
    try:
        utc_dt = datetime_original.astimezone(timezone.utc)
        utc_time = utc_dt.strftime("%Y:%m:%d %H:%M:%S")

        result = exiftool.write_tags(file_path, [
            f"-QuickTime:CreateDate={utc_time}",
            f"-QuickTime:MediaCreateDate={utc_time}",
        ])
        if file_path in _exif_cache:
            del _exif_cache[file_path]
        return result
    except Exception as e:
        print(f"Error writing QuickTime CreateDate: {e}", file=sys.stderr)
        return False


def get_all_timestamp_data(file_path: str, timezone_offset: Optional[str] = None, infer_from_filename: bool = False) -> dict:
    """Get all current timestamp data from file.

    When infer_from_filename=True:
    - Requires timezone_offset to be provided
    - Uses filename timestamp with provided timezone as source of truth
    - Ignores existing EXIF timestamps
    """
    data = {
        "file_path": file_path,
        "exif": read_exif_data(file_path),
        "file_system": get_file_system_timestamps(file_path) if sys.platform == "darwin" else {"birth": "", "modify": ""},
        "datetime_original_str": "",
        "datetime_original": None,
        "timestamp_source": "",
        "timezone_source": ""
    }

    if infer_from_filename:
        if not timezone_offset:
            raise ValueError("--infer-from-filename requires --timezone to be specified")
        report = read_timestamp_sources(file_path, timezone_offset)
        if not report.filename_parseable:
            raise ValueError(f"--infer-from-filename specified but filename has no parseable date")
        fn_ts, _ = parse_filename_timestamp(file_path)
        datetime_with_tz = f"{fn_ts}{timezone_offset}"
        data["datetime_original_str"] = datetime_with_tz
        data["datetime_original"] = parse_datetime_original(datetime_with_tz)
        data["timestamp_source"] = "filename (infer mode)"
        data["timezone_source"] = f"--timezone flag ({timezone_offset})"
        return data

    # Use 6-tier priority system to find best timestamp
    best_timestamp, source = get_best_timestamp(file_path, timezone_offset)
    data["timestamp_source"] = source

    if best_timestamp:
        if source == "CreationDate with timezone":
            data["datetime_original_str"] = data["exif"].get("CreationDate", "")
            data["timezone_source"] = "Keys:CreationDate metadata"
            if data["datetime_original_str"]:
                data["datetime_original"] = parse_datetime_original(data["datetime_original_str"])
        elif source == "DateTimeOriginal with timezone":
            data["datetime_original_str"] = data["exif"].get("DateTimeOriginal", "")
            data["timezone_source"] = "DateTimeOriginal metadata"
            if data["datetime_original_str"]:
                data["datetime_original"] = parse_datetime_original(data["datetime_original_str"])
        elif source == "DateTimeOriginal" and timezone_offset:
            datetime_with_tz = f"{best_timestamp}{timezone_offset}"
            data["datetime_original_str"] = datetime_with_tz
            data["datetime_original"] = parse_datetime_original(datetime_with_tz)
            data["timezone_source"] = f"--timezone flag ({timezone_offset})"
        elif source == "DateTimeOriginal":
            data["datetime_original_str"] = data["exif"].get("DateTimeOriginal", "")
            data["timezone_source"] = "DateTimeOriginal metadata"
            if data["datetime_original_str"]:
                data["datetime_original"] = parse_datetime_original(data["datetime_original_str"])
        elif source == "CreationDate with Z (UTC)" and timezone_offset:
            utc_dt = datetime.strptime(best_timestamp, "%Y:%m:%d %H:%M:%S").replace(tzinfo=timezone.utc)
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
        elif source == "MediaCreateDate" and timezone_offset:
            utc_dt = datetime.strptime(best_timestamp, "%Y:%m:%d %H:%M:%S").replace(tzinfo=timezone.utc)
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
            if timezone_offset:
                datetime_with_tz = f"{best_timestamp}{timezone_offset}"
                data["datetime_original_str"] = datetime_with_tz
                data["datetime_original"] = parse_datetime_original(datetime_with_tz)
                data["timezone_source"] = f"--timezone flag ({timezone_offset})"

    return data

def check_keys_creationdate_needs_update(file_path: str, datetime_original: datetime) -> bool:
    """Check if Keys:CreationDate needs updating

    Args:
        file_path: Path to the media file
        datetime_original: datetime object with timezone info

    Returns:
        True if Keys:CreationDate needs updating, False otherwise
    """
    exif_data = read_exif_data(file_path)
    current_creation_date = exif_data.get("CreationDate", "")

    if not current_creation_date:
        # Missing, needs to be written
        return True

    # Expected: DateTimeOriginal with its original timezone
    expected_value = datetime_original.strftime('%Y:%m:%d %H:%M:%S%z')
    # Format timezone with colon
    expected_value = re.sub(r'([+-]\d{2})(\d{2})$', r'\1:\2', expected_value)

    # Normalize both values for comparison (handle timezone format differences)
    current_norm = normalize_exif_value(current_creation_date)
    expected_norm = normalize_exif_value(expected_value)

    return current_norm != expected_norm

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

def determine_needed_changes(file_path: str, datetime_original: datetime, preserve_wallclock: bool = False) -> dict:
    """Determine what changes are needed

    Args:
        file_path: Path to the media file
        datetime_original: datetime object with timezone info
        preserve_wallclock: If True, preserve wall-clock shooting time for birth time

    Returns:
        Dictionary with boolean flags for needed changes
    """
    changes = {
        "keys_creationdate": False,
        "file_timestamps": False,
        "quicktime_createdate": False
    }

    # Check if Keys:CreationDate needs updating (always uses original timezone)
    changes["keys_creationdate"] = check_keys_creationdate_needs_update(file_path, datetime_original)

    # Check if file system timestamps need updating (macOS only)
    if sys.platform == "darwin":
        changes["file_timestamps"] = check_file_system_timestamps_need_update(file_path, datetime_original, preserve_wallclock)

    # Check if QuickTime CreateDate needs updating
    changes["quicktime_createdate"] = check_quicktime_createdate_needs_update(file_path, datetime_original)

    return changes


def _get_raw_original_time(current_data: dict) -> str:
    """Get the raw original timestamp from the actual source field for machine output.

    Returns the EXIF field value that was used as the timestamp source,
    falling back through common fields if the source-specific field is empty.
    """
    exif = current_data.get("exif", {})
    source = current_data.get("timestamp_source", "")

    if "DateTimeOriginal" in source:
        val = exif.get("DateTimeOriginal", "")
        if val:
            return val
    if "CreationDate" in source:
        val = exif.get("CreationDate", "")
        if val:
            return val
    if "MediaCreateDate" in source:
        val = exif.get("MediaCreateDate", "")
        if val:
            return val

    # Fallback: first non-empty common timestamp field
    for field in ["DateTimeOriginal", "CreationDate", "MediaCreateDate", "CreateDate"]:
        val = exif.get(field, "")
        if val:
            return val
    return ""


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
        birth_ts = current_data["file_system"].get("birth", "")
        if media_create:
            parts.append(f"{format_exif_timestamp_display(media_create)} UTC (MediaCreateDate)")
        if birth_ts:
            parts.append(f"{format_exif_timestamp_display(birth_ts)} local (file)")
    elif "filename" in source:
        # Show the parsed filename timestamp
        filename_ts, _ = parse_filename_timestamp(current_data.get("file_path", ""))
        if filename_ts:
            parts.append(f"{format_exif_timestamp_display(filename_ts)} (from filename)")
        else:
            parts.append(f"(from filename)")
    elif source == "file birthtime":
        birth_ts = current_data["file_system"].get("birth", "")
        if birth_ts:
            parts.append(f"{format_exif_timestamp_display(birth_ts)} (file birth)")
    elif source == "file mtime":
        mod_ts = current_data["file_system"].get("modify", "")
        if mod_ts:
            parts.append(f"{format_exif_timestamp_display(mod_ts)} (file modified)")

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
    """Format time delta showing hours, rounded to nearest hour if within 2 minutes"""
    sign = "+" if seconds > 0 else "-"
    total_seconds = abs(seconds)
    total_minutes = total_seconds / 60
    hours = total_minutes / 60

    # Round to nearest hour if within 2 minutes of a whole hour
    nearest_hour = round(hours)
    if nearest_hour > 0 and abs(hours - nearest_hour) * 60 < 2:  # within 2 minutes
        return f"{sign}{nearest_hour} hour{'s' if nearest_hour != 1 else ''}"

    # Otherwise show exact hours and minutes
    hours = int(total_minutes // 60)
    minutes = int(total_minutes % 60)

    if minutes == 0:
        return f"{sign}{hours} hour{'s' if hours != 1 else ''}"
    elif hours == 0:
        return f"{sign}{minutes} minute{'s' if minutes != 1 else ''}"
    else:
        return f"{sign}{hours}h {minutes}m"

def format_change_description(changes: dict, timestamp_data: Optional[dict] = None, current_data: Optional[dict] = None, preserve_wallclock: bool = False, datetime_original: Optional[datetime] = None) -> str:
    """Format change description from changes data"""
    parts = []

    # Check if DateTimeOriginal needs to be written
    needs_datetime_original = current_data and not current_data.get("exif", {}).get("DateTimeOriginal")
    if needs_datetime_original:
        parts.append("DateTimeOriginal (missing)")

    if changes.get("keys_creationdate"):
        # Show helpful context for Keys:CreationDate change
        if current_data and datetime_original:
            creation_date = current_data.get("exif", {}).get("CreationDate", "")
            time_display = datetime_original.strftime('%H:%M')

            if preserve_wallclock:
                # Preserving wall-clock time, updating timezone
                current_tz_offset = time.strftime('%z')
                current_tz_formatted = f"{current_tz_offset[:3]}:{current_tz_offset[3:]}"

                # Extract current timezone from existing CreationDate if present
                if creation_date:
                    current_tz_match = re.search(r'([+-]\d{2}):?(\d{2})$', creation_date)
                    if current_tz_match:
                        old_tz = f"{current_tz_match.group(1)}:{current_tz_match.group(2)}"
                        parts.append(f"Keys:CreationDate ({old_tz} → {current_tz_formatted}, preserving {time_display} shooting time)")
                    else:
                        parts.append(f"Keys:CreationDate (adding {current_tz_formatted}, preserving {time_display} shooting time)")
                else:
                    parts.append(f"Keys:CreationDate (missing, setting to {time_display} in {current_tz_formatted})")
            else:
                # Updating to match DateTimeOriginal
                orig_tz = datetime_original.strftime('%z')
                orig_tz_formatted = f"{orig_tz[:3]}:{orig_tz[3:]}"
                if creation_date:
                    parts.append(f"Keys:CreationDate (updating to {orig_tz_formatted})")
                else:
                    parts.append(f"Keys:CreationDate (missing, setting to {time_display} with {orig_tz_formatted})")
        else:
            parts.append("Keys:CreationDate")

    if changes.get("file_timestamps"):
        if timestamp_data and timestamp_data.get("expected_time"):
            birth_delta = timestamp_data.get("birth_delta_seconds")
            current_birth_str = timestamp_data.get("current_birth")

            if birth_delta is not None and abs(birth_delta) > 1:
                expected_dt = datetime.strptime(timestamp_data["expected_time"], '%Y:%m:%d %H:%M:%S')

                # Check if dates differ (not just times)
                if current_birth_str:
                    current_birth_dt = datetime.strptime(current_birth_str, '%Y:%m:%d %H:%M:%S')
                    dates_differ = current_birth_dt.date() != expected_dt.date()
                else:
                    dates_differ = False

                if dates_differ:
                    # Show full date change: "2025-12-06 → 2025-10-05 10:00"
                    current_display = current_birth_dt.strftime('%Y-%m-%d %H:%M')
                    expected_display = expected_dt.strftime('%Y-%m-%d %H:%M')
                    parts.append(f"Birth time ({current_display} → {expected_display})")
                else:
                    # Same date, just show time change
                    delta_str = format_time_delta(birth_delta)
                    time_display = expected_dt.strftime('%H:%M')
                    if preserve_wallclock:
                        parts.append(f"Birth time ({delta_str} to {time_display}, shooting time)")
                    else:
                        system_tz_offset = time.strftime('%z')
                        system_tz_formatted = f"{system_tz_offset[:3]}:{system_tz_offset[3:]}"
                        parts.append(f"Birth time ({delta_str} to {time_display}, display time in {system_tz_formatted})")
            else:
                parts.append("Birth time")
        else:
            parts.append("Birth time")

    if changes.get("quicktime_createdate"):
        # Show what the current and expected QuickTime CreateDate values are
        if current_data and datetime_original:
            media_create = current_data.get("exif", {}).get("MediaCreateDate", "")
            # Expected is UTC
            expected_utc = datetime_original.astimezone(timezone.utc).strftime("%Y:%m:%d %H:%M:%S")

            if media_create:
                parts.append(f"QuickTime CreateDate ({format_exif_timestamp_display(media_create)} → {format_exif_timestamp_display(expected_utc)} UTC)")
            else:
                parts.append(f"QuickTime CreateDate (missing → {format_exif_timestamp_display(expected_utc)} UTC)")
        else:
            parts.append("QuickTime CreateDate")

    return ", ".join(parts) if parts else "No change"

def _source_to_machine_token(source: str) -> str:
    """Map human-readable timestamp source description to machine token."""
    source_lower = source.lower()
    if "filename" in source_lower:
        return "filename"
    if "datetimeoriginal" in source_lower:
        return "datetimeoriginal"
    if "creationdate" in source_lower:
        return "creationdate"
    if "mediacreatedate" in source_lower:
        return "mediacreatedate"
    if "birthtime" in source_lower or "birth" in source_lower:
        return "file_birth"
    if "mtime" in source_lower:
        return "file_mtime"
    return source_lower


def fix_media_timestamps(file_path: str, dry_run: bool = False, timezone_offset: Optional[str] = None, infer_from_filename: bool = False, preserve_wallclock: bool = False) -> bool:
    """Main function to fix media (photo/video) timestamps

    Args:
        file_path: Path to media file
        dry_run: If True, show changes without applying them
        timezone_offset: Timezone offset (e.g. +09:00) for files missing timezone
        infer_from_filename: If True, use filename timestamp as source of truth
        preserve_wallclock: If True, preserve literal wall-clock shooting time (10:30 stays 10:30)
                          If False (default), convert to current timezone for correct equivalent display
    """

    filename = os.path.basename(file_path)

    detected_tz = extract_metadata_timezone(file_path)
    if detected_tz:
        print(f"@@timezone={detected_tz}")

    # Timezone mismatch detection (informational only)
    tz_mismatch = False
    if timezone_offset and not infer_from_filename:
        exif_data = read_exif_data(file_path)
        dto_value = exif_data.get("DateTimeOriginal", "")

        tz_match = re.search(r'([+-]\d{2}):?(\d{2})$', dto_value)
        if tz_match:
            existing_tz = f"{tz_match.group(1)}:{tz_match.group(2)}"
            provided_tz = normalize_timezone_input(timezone_offset)

            existing_tz_normalized = existing_tz.replace(':', '')
            provided_tz_normalized = provided_tz.replace(':', '')

            if existing_tz_normalized != provided_tz_normalized:
                tz_mismatch = True
                print(f"⚠️  Timezone mismatch: DateTimeOriginal has {existing_tz}, you provided {provided_tz}", file=sys.stderr)

    # Get all data
    current_data = get_all_timestamp_data(file_path, timezone_offset, infer_from_filename)

    # Display header
    print(f"\033[36m🔍 {filename}\033[0m", file=sys.stderr)

    if not current_data["datetime_original"]:
        # Check if we have CreateDate but missing timezone
        create_date = current_data["exif"].get("CreateDate", "")
        if create_date and not timezone_offset:
            print("❌ File has CreateDate but no DateTimeOriginal", file=sys.stderr)
            print(f"   CreateDate: {create_date}", file=sys.stderr)
            print("   Use --timezone to specify timezone (e.g., --timezone +09:00)", file=sys.stderr)
            print(f"@@file={filename}")
            print(f"@@original_time={create_date}")
            print(f"@@timestamp_action=error")
            return False
        print("❌ No valid DateTimeOriginal found", file=sys.stderr)
        print(f"@@file={filename}")
        print(f"@@timestamp_action=error")
        return False

    datetime_original = current_data["datetime_original"]
    datetime_original_str = current_data["datetime_original_str"]

    # Determine needed changes
    changes = determine_needed_changes(file_path, datetime_original, preserve_wallclock=preserve_wallclock)

    # Format and display timestamps
    original_display = format_original_timestamps(current_data)
    print(f"📅 Original : {original_display}", file=sys.stderr)

    timestamp_source = current_data.get("timestamp_source", "")
    timezone_source = current_data.get("timezone_source", "")
    corrected_display = format_corrected_timestamp(datetime_original, timestamp_source, timezone_source)
    print(f"⏱️ Corrected: {corrected_display}", file=sys.stderr)

    utc_dt = datetime_original.astimezone(timezone.utc)
    utc_display = utc_dt.strftime('%Y-%m-%d %H:%M:%S UTC')
    print(f"🌐 UTC      : {utc_display}", file=sys.stderr)

    # Gather timestamp data for display (separating data from presentation)
    timestamp_data = None
    if changes.get("file_timestamps"):
        current_fs = current_data["file_system"]
        expected_file_time = get_expected_file_system_time(datetime_original, preserve_wallclock=preserve_wallclock)

        timestamp_data = {
            "expected_time": expected_file_time,
            "current_birth": current_fs.get("birth"),
            "birth_delta_seconds": None
        }

        try:
            expected_dt = datetime.strptime(expected_file_time, '%Y:%m:%d %H:%M:%S')

            # Calculate birth time delta
            if current_fs.get("birth"):
                current_birth = datetime.strptime(current_fs["birth"], '%Y:%m:%d %H:%M:%S')
                timestamp_data["birth_delta_seconds"] = (expected_dt - current_birth).total_seconds()
        except:
            pass

    # Display changes
    change_desc = format_change_description(changes, timestamp_data, current_data, preserve_wallclock, datetime_original)
    has_changes = changes.get("keys_creationdate", False) or changes["file_timestamps"] or changes.get("quicktime_createdate", False)

    # Determine action for machine output
    action = "tz_mismatch" if tz_mismatch else None

    if dry_run and has_changes:
        print(f"📊 Change   : {change_desc} (DRY RUN)", file=sys.stderr)
        print(f"@@file={filename}")
        print(f"@@original_time={_get_raw_original_time(current_data)}")
        print(f"@@corrected_time={datetime_original_str}")
        print(f"@@timestamp_source={_source_to_machine_token(timestamp_source)}")
        print(f"@@correction_mode=timezone")
        print(f"@@timestamp_action={action or 'would_fix'}")
        return True
    else:
        print(f"📊 Change   : {change_desc}", file=sys.stderr)

    if not has_changes:
        print(f"@@file={filename}")
        print(f"@@original_time={_get_raw_original_time(current_data)}")
        print(f"@@corrected_time={datetime_original_str}")
        print(f"@@timestamp_source={_source_to_machine_token(timestamp_source)}")
        print(f"@@correction_mode=timezone")
        print(f"@@timestamp_action={action or 'no_change'}")
        return True

    if dry_run:
        return True

    # Apply changes
    success = True

    # Write DateTimeOriginal if:
    # 1. It's missing and we have timezone info, OR
    # 2. infer_from_filename is set (filename is the source of truth, DTO may be wrong/missing)
    should_write_datetime_original = (
        (not current_data["exif"].get("DateTimeOriginal") and current_data["datetime_original_str"]) or
        (infer_from_filename and current_data["datetime_original_str"])
    )

    if should_write_datetime_original and infer_from_filename and current_data["exif"].get("DateTimeOriginal"):
        print("   ⚠️  Overwriting existing DateTimeOriginal (--infer-from-filename flag)", file=sys.stderr)

    # Build all EXIF writes and apply in one exiftool call
    field_args = []
    if should_write_datetime_original:
        field_args.append(f"-DateTimeOriginal={current_data['datetime_original_str']}")
    if changes.get("keys_creationdate"):
        keys_value = datetime_original.strftime('%Y:%m:%d %H:%M:%S%z')
        keys_value = re.sub(r'([+-]\d{2})(\d{2})$', r'\1:\2', keys_value)
        field_args.append(f"-Keys:CreationDate={keys_value}")
    if changes.get("quicktime_createdate"):
        utc_time = datetime_original.astimezone(timezone.utc).strftime("%Y:%m:%d %H:%M:%S")
        field_args.append(f"-QuickTime:CreateDate={utc_time}")
        field_args.append(f"-QuickTime:MediaCreateDate={utc_time}")
    if field_args:
        if not write_exif_fields(file_path, field_args):
            if should_write_datetime_original:
                print("   ❌ Failed to write DateTimeOriginal", file=sys.stderr)
            if changes.get("keys_creationdate"):
                print("   ❌ Failed to write Keys:CreationDate", file=sys.stderr)
            if changes.get("quicktime_createdate"):
                print("   ❌ Failed to heal QuickTime CreateDate", file=sys.stderr)
            success = False

    # Update file system timestamps if needed
    if changes["file_timestamps"]:
        expected_file_timestamp = get_expected_file_system_time(datetime_original, preserve_wallclock=preserve_wallclock)
        if not set_file_system_timestamps(file_path, expected_file_timestamp):
            print("   ❌ Failed to apply file timestamps", file=sys.stderr)
            success = False

    # Emit machine-readable @@ lines
    print(f"@@file={filename}")
    print(f"@@original_time={_get_raw_original_time(current_data)}")
    print(f"@@corrected_time={datetime_original_str}")
    print(f"@@timestamp_source={_source_to_machine_token(timestamp_source)}")
    print(f"@@correction_mode=timezone")
    print(f"@@timestamp_action={'fixed' if success else 'error'}")

    return success

def main():
    """Command line interface"""
    parser = argparse.ArgumentParser(description='Fix media timestamps - ensures file system timestamps match EXIF data')
    parser.add_argument('file', help='Media file (photo or video) to process')
    parser.add_argument('--timezone', help='Timezone offset (e.g. +09:00) - required when DateTimeOriginal lacks timezone info')
    parser.add_argument('--country', help='Country code or name for automatic timezone lookup (e.g. JP, Taiwan)')
    parser.add_argument('--apply', action='store_true', help='Apply changes (default: dry run)')
    parser.add_argument('--infer-from-filename', action='store_true', help='Use filename timestamp as source of truth (requires --timezone)')
    parser.add_argument('--preserve-wallclock-time', action='store_true', help='Preserve literal wall-clock shooting time (10:30 stays 10:30) instead of converting to current timezone for display')

    args = parser.parse_args()

    # Convert file path to absolute path to ensure exiftool can find it
    file_path = os.path.abspath(args.file)

    # Handle country lookup for timezone
    timezone_offset = args.timezone
    if timezone_offset:
        # Normalize timezone format (add + sign if missing, ensure colon)
        timezone_offset = normalize_timezone_input(timezone_offset)

    if args.country and not timezone_offset:
        timezone_offset = get_timezone_for_country(args.country)
        if timezone_offset:
            print(f"→ Country: {get_country_name(args.country)} (timezone: {timezone_offset})", file=sys.stderr)
        else:
            print(f"Error: Could not determine timezone for country '{args.country}'", file=sys.stderr)
            return 1

    if args.infer_from_filename and not timezone_offset:
        print("Error: --infer-from-filename requires --timezone", file=sys.stderr)
        return 1

    success = fix_media_timestamps(
        file_path,
        dry_run=not args.apply,
        timezone_offset=timezone_offset,
        infer_from_filename=args.infer_from_filename,
        preserve_wallclock=args.preserve_wallclock_time
    )

    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())