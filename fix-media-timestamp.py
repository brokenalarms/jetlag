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
from datetime import datetime, timezone
from typing import Dict, Optional, Callable

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

# Declarative field mapping - each field knows how it should relate to DateTimeOriginal
FIELD_TRANSFORMS: Dict[str, Callable[[datetime], Optional[str]]] = {
    "CreateDate": same_as_original,
    "ModifyDate": same_as_original, 
    "MediaCreateDate": utc_from_date,
    "MediaModifyDate": utc_from_date,
    "Keys:CreationDate": remove_field,
    # File system timestamps - show same local time as DateTimeOriginal for FCP compatibility
    "FileModifyDate": same_local_time_current_tz,
    "FileAccessDate": same_local_time_current_tz,
}

# FileModifyDate and FileAccessDate are file system timestamps, not EXIF metadata
# They will be handled separately by set_file_system_timestamps()

def read_exif_data(file_path: str) -> Dict[str, str]:
    """Read all relevant EXIF data with single exiftool call"""
    fields = [
        "DateTimeOriginal", "CreateDate", "ModifyDate", 
        "MediaCreateDate", "MediaModifyDate", "Keys:CreationDate"
    ]
    
    cmd = ["exiftool", "-fast2", "-s"] + [f"-{field}" for field in fields] + [file_path]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        # Parse exiftool output
        data = {}
        for line in result.stdout.strip().split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                data[key.strip()] = value.strip()
        
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

def normalize_exif_value(value: str) -> str:
    """Normalize EXIF value for comparison (handle timezone format differences)"""
    if not value:
        return ""
    
    # Normalize timezone format: +02:00 <-> +0200
    return re.sub(r'([+-]\d{2}):(\d{2})$', r'\1\2', value)

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

def get_all_timestamp_data(file_path: str) -> dict:
    """Get all current timestamp data from file"""
    data = {
        "exif": read_exif_data(file_path),
        "file_system": get_file_system_timestamps(file_path),
        "datetime_original_str": "",
        "datetime_original": None
    }
    
    data["datetime_original_str"] = data["exif"].get("DateTimeOriginal", "")
    if data["datetime_original_str"]:
        data["datetime_original"] = parse_datetime_original(data["datetime_original_str"])
    
    return data

def calculate_expected_values(datetime_original: datetime) -> dict:
    """Calculate what all timestamp values should be"""
    expected = {}
    
    # Apply field transforms (includes both metadata and file system timestamps)
    for field, transform_func in FIELD_TRANSFORMS.items():
        expected[field] = transform_func(datetime_original)
    
    return expected

def determine_needed_changes(current_data: dict, expected_values: dict) -> dict:
    """Determine what changes are needed"""
    changes = {
        "metadata": {},
        "file_timestamps": False
    }
    
    # File system timestamp fields
    file_system_fields = {"FileModifyDate", "FileAccessDate"}
    
    # Check all fields declaratively
    for field, expected in expected_values.items():
        if field in file_system_fields:
            # Check file system timestamps
            current_fs = current_data["file_system"]
            current_modify = current_fs.get("modify", "")
            if current_modify != expected:
                changes["file_timestamps"] = True
        else:
            # Check metadata fields
            current = current_data["exif"].get(field, "")
            current_norm = normalize_exif_value(current)
            expected_norm = normalize_exif_value(expected) if expected else ""
            
            if current_norm != expected_norm:
                changes["metadata"][field] = expected
    
    return changes

def format_original_timestamps(current_data: dict) -> str:
    """Format original timestamp display from raw data"""
    parts = []
    
    # DateTimeOriginal first (source of truth when present)
    datetime_original = current_data["exif"].get("DateTimeOriginal", "")
    if datetime_original:
        parts.append(f"{datetime_original} (DateTimeOriginal)")
    
    # File timestamp as secondary (only if different from DateTimeOriginal or DateTimeOriginal not present)
    file_ts = current_data["file_system"].get("modify", "")
    if file_ts and not datetime_original:
        parts.append(f"{file_ts} (file)")
    
    # MediaCreateDate as tertiary info
    media_create = current_data["exif"].get("MediaCreateDate", "")
    if media_create:
        parts.append(f"{media_create} (MediaCreateDate)")
    
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
    if not changes["metadata"] and not changes["file_timestamps"]:
        return "No change"
    
    parts = []
    if changes["metadata"]:
        parts.append(f"Metadata: {', '.join(changes['metadata'].keys())}")
    if changes["file_timestamps"]:
        parts.append("File timestamps")
    
    return ", ".join(parts)

def fix_media_timestamps(file_path: str, dry_run: bool = False, verbose: bool = False) -> bool:
    """Main function to fix media (photo/video) timestamps"""
    
    # Get all data
    current_data = get_all_timestamp_data(file_path)
    
    # Display header
    filename = os.path.basename(file_path)
    print(f"\033[36m🔍 {filename}\033[0m")
    
    if not current_data["datetime_original"]:
        print("❌ No valid DateTimeOriginal found")
        return False
    
    datetime_original = current_data["datetime_original"]
    expected_values = calculate_expected_values(datetime_original)
    changes = determine_needed_changes(current_data, expected_values)
    
    # Format and display timestamps
    original_display = format_original_timestamps(current_data)
    print(f"📅 Original : {original_display}")
    
    corrected_display = format_corrected_timestamp(datetime_original)
    print(f"⏱️ Corrected: {corrected_display}")
    
    utc_display = datetime_original.astimezone(timezone.utc).strftime('%Y:%m:%d %H:%M:%S UTC')
    print(f"🌐 UTC      : {utc_display}")
    
    # Display changes
    change_desc = format_change_description(changes)
    if dry_run and (changes["metadata"] or changes["file_timestamps"]):
        print(f"📊 Change   : {change_desc} (DRY RUN)")
        return True
    else:
        print(f"📊 Change   : {change_desc}")
    
    if not changes["metadata"] and not changes["file_timestamps"]:
        return True
    
    if dry_run:
        return True
    
    # Apply changes
    success = True
    
    if changes["metadata"]:
        success = apply_exif_changes(file_path, changes["metadata"])
    
    if success and changes["file_timestamps"]:
        expected_file_timestamp = expected_values["FileModifyDate"]
        success = set_file_system_timestamps(file_path, expected_file_timestamp)
    
    if success:
        print("   ✅ Applied")
    else:
        print("   ❌ Failed")
        
    return success

def main():
    """Command line interface"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Fix media timestamps - ensures file system timestamps match EXIF data')
    parser.add_argument('file', help='Media file (photo or video) to process')
    parser.add_argument('--apply', action='store_true', help='Apply changes (default: dry run)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    success = fix_media_timestamps(args.file, dry_run=not args.apply, verbose=args.verbose)
    
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