#!/usr/bin/env python3
"""
Media timestamp fixing script - Python implementation
Declaratively fixes photo and video metadata timestamps
Ensures file system timestamps match EXIF data for both photos and videos
"""

import subprocess
import sys
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Callable

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
    """Get the expected file system timestamp (displays original shooting time in current TZ)"""
    # Extract the local time components from the original shooting time
    # When this gets written as epoch seconds, it will be interpreted in current system timezone
    # This makes FCP display the original shooting time (e.g., 3:39 PM) regardless of current TZ
    # Example: Shot at 3:39 PM CEST, file timestamp set so it displays as 3:39 PM in JST
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
            from datetime import timezone, timedelta
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
        
    cmd = ["exiftool", "-fast2", "-overwrite_original"]
    
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
        cmd = ["exiftool", "-overwrite_original", f"-DateTimeOriginal={datetime_with_tz}", file_path]
        subprocess.run(cmd, capture_output=True, check=True)
        # Invalidate cache since file was modified
        if file_path in _exif_cache:
            del _exif_cache[file_path]
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error writing DateTimeOriginal: {e}", file=sys.stderr)
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

def get_best_timestamp(file_path: str, timezone_offset: Optional[str] = None) -> tuple[Optional[str], str]:
    """Get the best timestamp using 5-tier priority system from bash lib-timestamp.sh
    Returns: (timestamp_string, source_description)
    """
    exif_data = read_exif_data(file_path)
    file_timestamps = get_file_system_timestamps(file_path)
    base = os.path.basename(file_path)

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
        return timestamp, "MediaCreateDate"

    # Priority 6: File timestamps
    if file_timestamps.get("birth"):
        return file_timestamps["birth"], "file birthtime"
    elif file_timestamps.get("modify"):
        return file_timestamps["modify"], "file mtime"

    return None, "no timestamps found"

def get_all_timestamp_data(file_path: str, timezone_offset: Optional[str] = None) -> dict:
    """Get all current timestamp data from file"""
    data = {
        "exif": read_exif_data(file_path),
        "file_system": get_file_system_timestamps(file_path),
        "datetime_original_str": "",
        "datetime_original": None,
        "timestamp_source": ""
    }

    # Use 5-tier priority system to find best timestamp
    best_timestamp, source = get_best_timestamp(file_path, timezone_offset)
    data["timestamp_source"] = source

    if best_timestamp:
        if source == "CreationDate with timezone":
            # Use existing CreationDate with timezone
            data["datetime_original_str"] = data["exif"].get("CreationDate", "")
            if data["datetime_original_str"]:
                data["datetime_original"] = parse_datetime_original(data["datetime_original_str"])
        elif source in ["DateTimeOriginal with timezone", "DateTimeOriginal"]:
            # Use existing DateTimeOriginal
            data["datetime_original_str"] = data["exif"].get("DateTimeOriginal", "")
            if data["datetime_original_str"]:
                data["datetime_original"] = parse_datetime_original(data["datetime_original_str"])
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
        else:
            # For filename or file timestamps, need timezone to create proper timestamp
            if timezone_offset:
                datetime_with_tz = f"{best_timestamp}{timezone_offset}"
                data["datetime_original_str"] = datetime_with_tz
                data["datetime_original"] = parse_datetime_original(datetime_with_tz)

    return data

def check_file_system_timestamps_need_update(file_path: str, datetime_original: datetime) -> bool:
    """Check if file system timestamps need updating to match original shooting time"""
    current_fs = get_file_system_timestamps(file_path)
    expected_time = get_expected_file_system_time(datetime_original)

    # Check if either birth time or modify time differs from expected (allow 60 second tolerance)
    birth_needs_update = False
    modify_needs_update = False

    if current_fs.get("birth"):
        try:
            current_birth = datetime.strptime(current_fs["birth"], '%Y:%m:%d %H:%M:%S')
            expected_dt = datetime.strptime(expected_time, '%Y:%m:%d %H:%M:%S')
            diff = abs((current_birth - expected_dt).total_seconds())
            birth_needs_update = diff > 60
        except:
            birth_needs_update = True

    if current_fs.get("modify"):
        try:
            current_modify = datetime.strptime(current_fs["modify"], '%Y:%m:%d %H:%M:%S')
            expected_dt = datetime.strptime(expected_time, '%Y:%m:%d %H:%M:%S')
            diff = abs((current_modify - expected_dt).total_seconds())
            modify_needs_update = diff > 60
        except:
            modify_needs_update = True

    return birth_needs_update or modify_needs_update

def determine_needed_changes(file_path: str, datetime_original: datetime) -> dict:
    """Determine what changes are needed - only file system timestamps"""
    changes = {
        "file_timestamps": False
    }

    # Only check if file system timestamps need updating
    changes["file_timestamps"] = check_file_system_timestamps_need_update(file_path, datetime_original)

    return changes

def format_original_timestamps(current_data: dict) -> str:
    """Format original timestamp display from raw data"""
    parts = []

    # Show the timestamp source that was actually used
    source = current_data.get("timestamp_source", "")

    if source == "DateTimeOriginal with timezone":
        datetime_original = current_data["exif"].get("DateTimeOriginal", "")
        if datetime_original:
            parts.append(f"{datetime_original} (DateTimeOriginal)")
    elif source == "CreationDate with timezone":
        creation_date = current_data["exif"].get("CreationDate", "")
        if creation_date:
            parts.append(f"{creation_date} (CreationDate)")
    elif source == "DateTimeOriginal":
        datetime_original = current_data["exif"].get("DateTimeOriginal", "")
        if datetime_original:
            parts.append(f"{datetime_original} (DateTimeOriginal)")
    elif source == "MediaCreateDate":
        media_create = current_data["exif"].get("MediaCreateDate", "")
        if media_create:
            parts.append(f"{media_create} (MediaCreateDate)")
    elif source == "filename":
        parts.append(f"(from filename)")
    elif source in ["file birthtime", "file mtime"]:
        file_ts = current_data["file_system"].get("modify", "")
        if file_ts:
            parts.append(f"{file_ts} (file)")

    # Also show additional context
    if source == "MediaCreateDate":
        file_ts = current_data["file_system"].get("modify", "")
        if file_ts:
            parts.append(f"{file_ts} (file)")

    return ", ".join(parts) if parts else "(no timestamps available)"

def format_corrected_timestamp(datetime_original: datetime) -> str:
    """Format corrected timestamp display"""
    corrected_str = same_as_original(datetime_original)
    tz_value = datetime_original.strftime('%z')
    # Format timezone with colon
    tz_formatted = f"{tz_value[:3]}:{tz_value[3:]}" if len(tz_value) == 5 else tz_value
    
    return f"{corrected_str} (from DateTimeOriginal with timezone, tz: DateTimeOriginal metadata ({tz_formatted}))"

def format_change_description(changes: dict) -> str:
    """Format change description from changes data"""
    if not changes["file_timestamps"]:
        return "No change"

    return "File timestamps"

def fix_media_timestamps(file_path: str, dry_run: bool = False, verbose: bool = False, timezone_offset: Optional[str] = None) -> bool:
    """Main function to fix media (photo/video) timestamps"""
    
    # Get all data
    current_data = get_all_timestamp_data(file_path, timezone_offset)
    
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
    
    corrected_display = format_corrected_timestamp(datetime_original)
    print(f"⏱️ Corrected: {corrected_display}")
    
    utc_display = datetime_original.astimezone(timezone.utc).strftime('%Y:%m:%d %H:%M:%S UTC')
    print(f"🌐 UTC      : {utc_display}")
    
    # Display changes
    change_desc = format_change_description(changes)
    if dry_run and changes["file_timestamps"]:
        print(f"📊 Change   : {change_desc} (DRY RUN)")
        return True
    else:
        print(f"📊 Change   : {change_desc}")

    if not changes["file_timestamps"]:
        return True

    if dry_run:
        return True

    # Apply changes
    success = True

    # Write DateTimeOriginal if it's missing and we have timezone info
    if not current_data["exif"].get("DateTimeOriginal") and current_data["datetime_original_str"]:
        if write_datetime_original(file_path, current_data["datetime_original_str"]):
            print("   ✅ Wrote DateTimeOriginal")
        else:
            print("   ❌ Failed to write DateTimeOriginal")
            success = False

    if changes["file_timestamps"]:
        expected_file_timestamp = get_expected_file_system_time(datetime_original)
        if set_file_system_timestamps(file_path, expected_file_timestamp):
            print("   ✅ Applied file timestamps")
        else:
            print("   ❌ Failed to apply file timestamps")
            success = False

    if success:
        print("✅ Complete")
    else:
        print("❌ Failed")

    return success

def main():
    """Command line interface"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Fix media timestamps - ensures file system timestamps match EXIF data')
    parser.add_argument('file', help='Media file (photo or video) to process')
    parser.add_argument('--timezone', help='Timezone offset (e.g. +09:00) - required when DateTimeOriginal lacks timezone info')
    parser.add_argument('--country', help='Country code or name for automatic timezone lookup (e.g. JP, Taiwan)')
    parser.add_argument('--apply', action='store_true', help='Apply changes (default: dry run)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()

    # Handle country lookup for timezone
    timezone_offset = args.timezone
    if args.country and not timezone_offset:
        timezone_offset = get_timezone_for_country(args.country)
        if timezone_offset:
            print(f"→ Country: {get_country_name(args.country)} (timezone: {timezone_offset})")
        else:
            print(f"Error: Could not determine timezone for country '{args.country}'", file=sys.stderr)
            return 1

    success = fix_media_timestamps(args.file, dry_run=not args.apply, verbose=args.verbose, timezone_offset=timezone_offset)
    
    if success:
        if args.apply:
            print("✅ Media timestamp processing complete - changes applied.")
        else:
            print("✅ Media timestamp processing complete - DRY RUN (no changes made).")
    else:
        print("❌ Media timestamp processing failed.")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())