"""
Shared timestamp source analysis.

Reads a file and reports what timestamps are available from which sources.
Used by fix-media-timestamp.py, report-file-dates.py, and media-pipeline.py.

Public API:
    read_timestamp_sources(file_path, ...) -> TimestampReport
    build_filename(original_name, corrected_date) -> Optional[str]
"""

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from lib.metadata import metadata_service as exiftool

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
        print(f"❌ {e}", file=__import__('sys').stderr)
        return {}
    except Exception as e:
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


_UTC_TIMESTAMP_SOURCES = {"CreationDate with Z (UTC)", "MediaCreateDate"}


def is_utc_timestamp_source(source: str) -> bool:
    """True when a source's timestamp is UTC rather than local wall-clock time."""
    return source in _UTC_TIMESTAMP_SOURCES


def is_zone_name(timezone_spec: str) -> bool:
    """True when the spec is an IANA zone name rather than a fixed +HHMM offset."""
    if not timezone_spec:
        return False
    return not re.match(r'^[+-]?\d{2}:?\d{2}$', timezone_spec)


def resolve_timezone_offset(
    timezone_spec: Optional[str],
    timestamp: Optional[str],
    timestamp_is_utc: bool = False,
) -> Optional[str]:
    """Resolve a timezone spec to the +HH:MM offset in effect at a given timestamp.

    A fixed offset passes through normalized. A zone name is resolved against the
    timestamp, so a DST zone yields the offset that applied when the file was shot
    rather than the offset in effect today. Local timestamps inside the repeated
    hour of a DST changeover resolve to the first occurrence.
    """
    if not timezone_spec:
        return timezone_spec
    if not is_zone_name(timezone_spec):
        return normalize_timezone_input(timezone_spec)

    try:
        zone = ZoneInfo(timezone_spec)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"Unknown timezone: {timezone_spec}")

    if not timestamp:
        raise ValueError(f"Cannot resolve {timezone_spec} without a timestamp")

    naive = datetime.strptime(timestamp, "%Y:%m:%d %H:%M:%S")
    if timestamp_is_utc:
        local = naive.replace(tzinfo=timezone.utc).astimezone(zone)
    else:
        local = naive.replace(tzinfo=zone)

    return ensure_colon_tz(local.strftime("%z"))


def resolve_file_timezone_offset(file_path: str, timezone_spec: Optional[str]) -> Optional[str]:
    """Resolve a timezone spec to the offset that applies to one file's own timestamp."""
    if not timezone_spec:
        return None
    best_timestamp, source = get_best_timestamp(file_path, timezone_spec)
    return resolve_timezone_offset(
        timezone_spec, best_timestamp, is_utc_timestamp_source(source)
    )


def normalize_exif_value(value: str) -> str:
    """Normalize EXIF value for comparison (handle timezone format differences)."""
    if not value:
        return ""
    return normalize_timezone_format(value)


# ---------------------------------------------------------------------------
# Filename timestamp parsing — generic date patterns
# ---------------------------------------------------------------------------

_PATTERNS_FILE = Path(__file__).parent / "filename-patterns.json"
_FILENAME_PATTERNS = [
    (re.compile(p["regex"]), p["name"], p["has_time"])
    for p in json.loads(_PATTERNS_FILE.read_text())
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

_MIN_ZONE_OFFSET = timedelta(hours=-12)
_MAX_ZONE_OFFSET = timedelta(hours=14)


def _is_legal_zone_offset(delta: timedelta) -> bool:
    """Whether a difference from UTC is one a real zone uses: -12:00 to +14:00,
    in quarter-hour steps."""
    if not _MIN_ZONE_OFFSET <= delta <= _MAX_ZONE_OFFSET:
        return False
    return delta.total_seconds() % 900 == 0


def _quicktime_is_instant(quicktime_timestamp: str, filename_timestamp: Optional[str]) -> bool:
    """Whether a QuickTime date and a filename describe one instant in some zone.

    QuickTime dates are UTC by specification, but not every device honours that and a
    camera clock can simply be wrong. The filename is the camera's own local reading, so
    a legal zone offset between the two is what shows the QuickTime date to be an instant.
    """
    if not (quicktime_timestamp and filename_timestamp):
        return False
    try:
        quicktime = datetime.strptime(quicktime_timestamp, "%Y:%m:%d %H:%M:%S")
        local = datetime.strptime(filename_timestamp, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return False

    delta = local - quicktime
    if delta == timedelta(0):
        # Identical values cannot separate a camera at UTC+0 from one writing local
        # time into a field defined as UTC.
        return False
    return _is_legal_zone_offset(delta)


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

    media_create_date = exif_data.get("MediaCreateDate", "")
    media_timestamp = ""
    if media_create_date and re.search(r'[0-9]', media_create_date):
        candidate = re.sub(
            r'([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}).*', r'\1',
            media_create_date)
        if is_valid_timestamp(candidate):
            media_timestamp = candidate

    ts, _ = parse_filename_timestamp(file_path)

    # Priority 3: a QuickTime date the filename shows to be an instant. A camera left on
    # the previous country's time writes a filename that is wrong for where it was shot;
    # the instant survives that, so it wins where the two contradict each other. Without
    # a declared timezone there is nothing to convert the instant into.
    if timezone_offset and _quicktime_is_instant(media_timestamp, ts):
        return media_timestamp, "MediaCreateDate"

    # Priority 4: Filename for VID/IMG/LRV/DJI
    if ts and (re.match(r'^(VID|LRV|IMG)_[0-9]{8}_[0-9]{6}', base) or
               re.match(r'^DJI_[0-9]{14}_', base)):
        return ts, "filename"

    # Priority 5: DateTimeOriginal without timezone
    if datetime_original and re.search(r'[0-9]', datetime_original):
        timestamp = re.sub(
            r'([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}).*', r'\1',
            datetime_original)
        return timestamp, "DateTimeOriginal"

    # Priority 6: MediaCreateDate with nothing to cross-check it against
    if media_timestamp:
        return media_timestamp, "MediaCreateDate"

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
