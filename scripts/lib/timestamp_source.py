"""
Shared timestamp source analysis.

Reads a file and reports what timestamps are available from which sources.
Used by fix-media-timestamp.py, report-file-dates.py, and media-pipeline.py.

Public API:
    read_timestamp_sources(file_path, ...) -> TimestampReport
    build_filename(original_name, corrected_date) -> Optional[str]
"""

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

from lib.exiftool import exiftool

# ---------------------------------------------------------------------------
# EXIF cache — shared across all callers within a process
# ---------------------------------------------------------------------------

_exif_cache: Dict[str, Dict[str, str]] = {}


def read_exif_data(file_path: str) -> Dict[str, str]:
    """Read all relevant EXIF timestamp fields with single exiftool call (cached)."""
    if file_path in _exif_cache:
        return _exif_cache[file_path]

    fields = [
        "DateTimeOriginal", "CreateDate", "ModifyDate", "CreationDate",
        "QuickTime:MediaCreateDate", "QuickTime:MediaModifyDate", "Keys:CreationDate"
    ]

    try:
        raw = exiftool.read_tags(file_path, fields)

        data = {}
        for key, value in raw.items():
            if key == "MediaCreateDate":
                data["MediaCreateDate"] = value
            elif key == "MediaModifyDate":
                data["MediaModifyDate"] = value
            else:
                data[key] = value

        _exif_cache[file_path] = data
        return data
    except FileNotFoundError as e:
        from pathlib import Path
        print(f"❌ {e}", file=__import__('sys').stderr)
        return {}
    except Exception as e:
        from pathlib import Path
        print(f"❌ EXIF read failed for {os.path.basename(file_path)}: {e}",
              file=__import__('sys').stderr)
        return {}


def clear_exif_cache(file_path: str = None):
    """Clear the EXIF cache for a specific file or all files."""
    if file_path:
        _exif_cache.pop(file_path, None)
    else:
        _exif_cache.clear()


# ---------------------------------------------------------------------------
# Timestamp validation / parsing helpers
# ---------------------------------------------------------------------------

def is_valid_timestamp(timestamp_str: str) -> bool:
    """Check if timestamp is valid (not null/zero date)."""
    if not timestamp_str:
        return False
    if timestamp_str.startswith("0000:00:00"):
        return False
    return True


def parse_datetime_original(datetime_str: str) -> Optional[datetime]:
    """Parse EXIF datetime string (with timezone) to datetime object."""
    if not datetime_str:
        return None

    pattern = r'^(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})([\+\-]\d{2}):?(\d{2})$'
    match = re.match(pattern, datetime_str)

    if match:
        year, month, day, hour, minute, second, tz_hour, tz_min = match.groups()

        try:
            dt_str = f"{year}-{month}-{day} {hour}:{minute}:{second}"
            dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
            tz_sign = 1 if tz_hour.startswith('+') else -1
            tz_hours = int(tz_hour[1:])
            tz_minutes = int(tz_min)
            tz_offset = tz_sign * (tz_hours * 60 + tz_minutes)
            tz = timezone(timedelta(minutes=tz_offset))
            return dt.replace(tzinfo=tz)
        except ValueError:
            return None

    return None


# ---------------------------------------------------------------------------
# Timezone normalization
# ---------------------------------------------------------------------------

def ensure_colon_tz(tz_str: str) -> str:
    """Ensure timezone has colon format (+0200 -> +02:00, +02:00 stays +02:00)."""
    return re.sub(r'([+-][0-9]{2}):?([0-9]{2})$', r'\1:\2', tz_str)


def normalize_timezone_input(tz_str: str) -> str:
    """Normalize timezone input — ensure it has +/- sign and colon format."""
    if not tz_str:
        return tz_str
    if not tz_str.startswith(('+', '-')):
        tz_str = '+' + tz_str
    return ensure_colon_tz(tz_str)


def normalize_timezone_format(value: str) -> str:
    """Normalize timezone format for consistent comparison (remove colon)."""
    if not value:
        return ""
    return re.sub(r'([+-]\d{2}):(\d{2})$', r'\1\2', value)


def normalize_exif_value(value: str) -> str:
    """Normalize EXIF value for comparison (handle timezone format differences)."""
    if not value:
        return ""
    return normalize_timezone_format(value)


# ---------------------------------------------------------------------------
# Filename timestamp parsing — generic date patterns
# ---------------------------------------------------------------------------

# Each pattern: (compiled regex for the date portion, pattern name, has_time)
# Order matters — most specific first.
_FILENAME_PATTERNS = [
    # YYYYMMDD_HHMMSS — e.g. VID_20250505_130334_00_001.mp4
    (re.compile(r'(\d{4})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])_((?:[01]\d|2[0-3])(?:[0-5]\d){2})'),
     'YYYYMMDD_HHMMSS', True),
    # YYYYMMDDHHMMSS — e.g. DJI_20250505130334_0001.mp4
    (re.compile(r'(\d{4})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])((?:[01]\d|2[0-3])(?:[0-5]\d){2})'),
     'YYYYMMDDHHMMSS', True),
    # YYYY-MM-DD + time with separators — e.g. Screenshot 2025-05-05 at 13.03.34.png
    (re.compile(r'(\d{4})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\s+at\s+(\d{1,2})\.(\d{2})\.(\d{2})'),
     'YYYY-MM-DD_at_HH.MM.SS', True),
    # YYYYMMDD (no time) — e.g. DSC_20250505_001.jpg
    (re.compile(r'(\d{4})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])'),
     'YYYYMMDD', False),
]


def parse_filename_timestamp(file_path: str) -> tuple[Optional[str], Optional[str]]:
    """Extract timestamp from generic date patterns in filename.

    Returns:
        (timestamp_str in "YYYY:MM:DD HH:MM:SS" format, pattern_name) or (None, None)
    """
    base = os.path.splitext(os.path.basename(file_path))[0]

    for pattern_re, pattern_name, has_time in _FILENAME_PATTERNS:
        match = pattern_re.search(base)
        if not match:
            continue

        groups = match.groups()

        if pattern_name == 'YYYYMMDD_HHMMSS':
            year, month, day, time_part = groups
            if not (2000 <= int(year) <= 2099):
                continue
            t = time_part
            return (f"{year}:{month}:{day} {t[0:2]}:{t[2:4]}:{t[4:6]}",
                    pattern_name)

        elif pattern_name == 'YYYYMMDDHHMMSS':
            year, month, day, time_part = groups
            if not (2000 <= int(year) <= 2099):
                continue
            t = time_part
            return (f"{year}:{month}:{day} {t[0:2]}:{t[2:4]}:{t[4:6]}",
                    pattern_name)

        elif pattern_name == 'YYYY-MM-DD_at_HH.MM.SS':
            year, month, day, hour, minute, second = groups
            if not (2000 <= int(year) <= 2099):
                continue
            return (f"{year}:{month}:{day} {int(hour):02d}:{minute}:{second}",
                    pattern_name)

        elif pattern_name == 'YYYYMMDD':
            year, month, day = groups
            if not (2000 <= int(year) <= 2099):
                continue
            return (f"{year}:{month}:{day} 00:00:00", pattern_name)

    return None, None


def build_filename(original_name: str, corrected_date: datetime) -> Optional[str]:
    """Replace the date portion of a filename with corrected_date.

    Detects the same generic date pattern that parse_filename_timestamp() uses,
    substitutes the new date in the same format, preserves everything else.

    Returns None if the filename has no parseable date pattern.
    """
    stem, ext = os.path.splitext(original_name)

    for pattern_re, pattern_name, has_time in _FILENAME_PATTERNS:
        match = pattern_re.search(stem)
        if not match:
            continue

        groups = match.groups()
        year = groups[0]
        if not (2000 <= int(year) <= 2099):
            continue

        if pattern_name == 'YYYYMMDD_HHMMSS':
            replacement = corrected_date.strftime('%Y%m%d_%H%M%S')
        elif pattern_name == 'YYYYMMDDHHMMSS':
            replacement = corrected_date.strftime('%Y%m%d%H%M%S')
        elif pattern_name == 'YYYY-MM-DD_at_HH.MM.SS':
            replacement = corrected_date.strftime('%Y-%m-%d at %H.%M.%S')
        elif pattern_name == 'YYYYMMDD':
            replacement = corrected_date.strftime('%Y%m%d')
        else:
            continue

        new_stem = stem[:match.start()] + replacement + stem[match.end():]
        return new_stem + ext

    return None


# ---------------------------------------------------------------------------
# Metadata timezone extraction
# ---------------------------------------------------------------------------

def extract_metadata_timezone(file_path: str) -> Optional[str]:
    """Extract timezone offset from DateTimeOriginal or CreationDate if present."""
    exif_data = read_exif_data(file_path)
    for field in ["DateTimeOriginal", "CreationDate"]:
        value = exif_data.get(field, "")
        if value:
            tz_match = re.search(r'([+-]\d{2}):?(\d{2})$', value)
            if tz_match:
                return f"{tz_match.group(1)}:{tz_match.group(2)}"
    return None


# ---------------------------------------------------------------------------
# Best timestamp (6-tier priority)
# ---------------------------------------------------------------------------

def get_best_timestamp(
    file_path: str,
    timezone_offset: Optional[str] = None,
) -> tuple[Optional[str], str]:
    """Get the best timestamp using 6-tier priority system.

    Returns: (timestamp_string, source_description)
    """
    exif_data = read_exif_data(file_path)
    base = os.path.basename(file_path)

    # Priority 1: DateTimeOriginal with timezone
    datetime_original = exif_data.get("DateTimeOriginal", "")
    if datetime_original and re.search(r'[+-]\d{2}:?\d{2}$', datetime_original):
        timestamp = re.sub(
            r'([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}).*', r'\1',
            datetime_original)
        return timestamp, "DateTimeOriginal with timezone"

    # Priority 2: CreationDate with timezone
    creation_date = exif_data.get("CreationDate", "")
    if creation_date and re.search(r'[+-]\d{2}:?\d{2}$', creation_date):
        timestamp = re.sub(
            r'([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}).*', r'\1',
            creation_date)
        return timestamp, "CreationDate with timezone"

    # Priority 2.5: Keys:CreationDate with Z marker
    if creation_date and creation_date.endswith('Z') and timezone_offset:
        timestamp = creation_date[:-1].strip()
        if re.match(r'[0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}', timestamp):
            return timestamp, "CreationDate with Z (UTC)"

    # Priority 3: Filename for VID/IMG/LRV/DJI
    ts, _ = parse_filename_timestamp(file_path)
    if ts and (re.match(r'^(VID|LRV|IMG)_[0-9]{8}_[0-9]{6}', base) or
               re.match(r'^DJI_[0-9]{14}_', base)):
        return ts, "filename"

    # Priority 4: DateTimeOriginal without timezone
    if datetime_original and re.search(r'[0-9]', datetime_original):
        timestamp = re.sub(
            r'([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}).*', r'\1',
            datetime_original)
        return timestamp, "DateTimeOriginal"

    # Priority 5: MediaCreateDate (usually UTC)
    media_create_date = exif_data.get("MediaCreateDate", "")
    if media_create_date and re.search(r'[0-9]', media_create_date):
        timestamp = re.sub(
            r'([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}).*', r'\1',
            media_create_date)
        if is_valid_timestamp(timestamp):
            return timestamp, "MediaCreateDate"

    # Priority 6: File timestamps
    try:
        st = os.stat(file_path)
        try:
            birth = datetime.fromtimestamp(st.st_birthtime).strftime('%Y:%m:%d %H:%M:%S')
            return birth, "file birthtime"
        except AttributeError:
            pass
        mtime = datetime.fromtimestamp(st.st_mtime).strftime('%Y:%m:%d %H:%M:%S')
        return mtime, "file mtime"
    except OSError:
        pass

    return None, "no timestamps found"


# ---------------------------------------------------------------------------
# TimestampReport — unified analysis
# ---------------------------------------------------------------------------

@dataclass
class TimestampReport:
    """Everything known about a file's available timestamps."""
    metadata_date: Optional[datetime]
    metadata_source: str
    metadata_tz: Optional[str]

    filename_parseable: bool
    filename_date: Optional[datetime]
    filename_pattern: Optional[str]


def read_timestamp_sources(
    file_path: str,
    timezone_offset: Optional[str] = None,
) -> TimestampReport:
    """Analyse a file and report all available timestamp sources."""
    # Metadata side — use the existing priority system
    best_ts, source = get_best_timestamp(file_path, timezone_offset)

    metadata_date = None
    metadata_tz = extract_metadata_timezone(file_path)

    if best_ts:
        try:
            metadata_date = datetime.strptime(best_ts, '%Y:%m:%d %H:%M:%S')
        except ValueError:
            pass

    # Filename side
    fn_ts, fn_pattern = parse_filename_timestamp(file_path)
    fn_parseable = fn_ts is not None
    fn_date = None
    if fn_ts:
        try:
            fn_date = datetime.strptime(fn_ts, '%Y:%m:%d %H:%M:%S')
        except ValueError:
            pass

    return TimestampReport(
        metadata_date=metadata_date,
        metadata_source=source,
        metadata_tz=metadata_tz,
        filename_parseable=fn_parseable,
        filename_date=fn_date,
        filename_pattern=fn_pattern,
    )
