"""
Shared timestamp source analysis.

Reads a file and reports what timestamps are available from which sources.
Used by lib/fix_media_timestamp/, lib/media_pipeline/, lib/tag_media.py and report-file-dates.

Every fact jetlag uses about a file's time comes from here, worked out once from
the file's one cached exiftool read: read_file() returns a FileReading, and every
consumer (the correction, the pipeline's pre-flight guards, the date folder) takes
the winning timestamp, the file's zone, the camera's zone setting, the filename's
time and the wall-clock time from it rather than deriving any of them itself.
tests/timestamps/test_one_derivation.py fails when anything outside lib/timestamps/
does.

Public API:
    read_file(file_path) -> FileReading
    read_timestamp_sources(file_path, ...) -> TimestampReport
    build_filename(original_name, corrected_date) -> Optional[str]
"""

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from lib import DATA_DIR
from lib.exiftool import exiftool

# ---------------------------------------------------------------------------
# EXIF reads, cached per file on the exiftool client (which drops a file's entry
# whenever it writes that file)
# ---------------------------------------------------------------------------

PRESERVED_FILENAME_TAG = "XMP-xmpMM:PreservedFileName"
# The movie header (mvhd) clock, read through the composite in exiftool-jetlag.config
# because an unqualified CreateDate in a QuickTime file prefers XMP.
MOVIE_HEADER_CREATE_DATE_TAG = "MovieHeaderCreateDate"

# Files imported before the jetlag XMP namespace carry their provenance as JSON in
# this tag instead; it is read only to know such a file is already recorded.
LEGACY_PROVENANCE_TAG = "XMP-xmpDM:LogComment"

# exiftool parses an Insta360 trailer, where these files record their camera Model,
# only under ExtractEmbedded. On other video it reads every timed-metadata track,
# which is cost nothing else here gains from.
EMBEDDED_DATA_SUFFIXES = {".insv", ".insp"}


def read_exif_data(file_path: str) -> Dict[str, str]:
    """Read all relevant EXIF timestamp fields with single exiftool call (cached)."""
    if file_path in exiftool.cache:
        return exiftool.cache[file_path]

    # The provenance tag and camera Make/Model ride along here rather than in reads
    # of their own: an extra exiftool round-trip per file costs more than every
    # field in this list.
    fields = [
        "DateTimeOriginal", "OffsetTimeOriginal", "CreateDate", "ModifyDate",
        "CreationDate", MOVIE_HEADER_CREATE_DATE_TAG, "QuickTime:MediaCreateDate",
        "QuickTime:MediaModifyDate",
        "QuickTime:TrackCreateDate", "Keys:CreationDate",
        PRESERVED_FILENAME_TAG, LEGACY_PROVENANCE_TAG,
        "Make", "Model",
    ]

    try:
        embedded = ["-ee"] if Path(file_path).suffix.lower() in EMBEDDED_DATA_SUFFIXES else None
        raw = exiftool.read_tags(file_path, fields, extra_args=embedded)

        data = dict(raw)
        _complete_datetime_original(data)
        exiftool.cache[file_path] = data
        return data
    except FileNotFoundError as e:
        print(f"❌ {e}", file=__import__('sys').stderr)
        return {}
    except Exception as e:
        print(f"❌ EXIF read failed for {os.path.basename(file_path)}: {e}",
              file=__import__('sys').stderr)
        return {}


def _complete_datetime_original(data: Dict[str, str]) -> None:
    """Attach OffsetTimeOriginal to a bare DateTimeOriginal, in place.

    Binary EXIF DateTimeOriginal is exactly 19 characters, so a still camera has
    nowhere to put a zone except OffsetTimeOriginal — which is always and only the
    zone of those digits. Joining them here means every reader of the cached dict
    sees one zoned value and ranks it as a zoned source, with no special case of
    its own.
    """
    datetime_original = data.get("DateTimeOriginal", "")
    if not datetime_original or re.search(r'[+-]\d{2}:?\d{2}$', datetime_original):
        return

    offset = ensure_colon_tz((data.get("OffsetTimeOriginal") or "").strip())
    if re.fullmatch(r'[+-]\d{2}:\d{2}', offset):
        data["DateTimeOriginal"] = f"{datetime_original}{offset}"


def carry_exif_cache(from_path: str, to_path: str) -> None:
    """Let a byte-identical copy of a file use the metadata already read from it."""
    if from_path in exiftool.cache:
        exiftool.cache[to_path] = exiftool.cache[from_path]


def clear_exif_cache(file_path: Optional[str] = None) -> None:
    """Forget cached metadata for one file, or for every file.

    Writes through lib.exiftool already do this; it is for a file changed some
    other way, such as by a separate exiftool process.
    """
    if file_path:
        exiftool.cache.pop(file_path, None)
    else:
        exiftool.cache.clear()


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


_TRAILING_ZONE_OR_UTC = re.compile(r'([+-]\d{2}:?\d{2}|Z)$')


def trailing_zone(value: Optional[str]) -> Optional[str]:
    """The zone a tag value carries at its end: '+HH:MM', 'Z', or None for a
    naive value."""
    match = _TRAILING_ZONE_OR_UTC.search(value or "")
    if not match:
        return None
    zone = match.group(1)
    return zone if zone == "Z" else ensure_colon_tz(zone)


def tzinfo_from_offset(offset_str: Optional[str]) -> Optional[timezone]:
    """A tzinfo for a '+HH:MM' / '+HHMM' offset string, or None if it is not one."""
    match = re.match(r'([+-])(\d{2}):?(\d{2})$', offset_str or "")
    if not match:
        return None
    sign, hours, minutes = match.groups()
    offset_seconds = int(hours) * 3600 + int(minutes) * 60
    if sign == '-':
        offset_seconds = -offset_seconds
    return timezone(timedelta(seconds=offset_seconds))


# ---------------------------------------------------------------------------
# Timestamp sources
# ---------------------------------------------------------------------------

class TimestampSource(Enum):
    """Where a file's best timestamp came from.

    display is the label shown to people, token the machine value emitted as
    timestamp_result.source (enumerated in pipeline-schema.yaml), is_utc whether
    the source's digits are UTC rather than local wall-clock time, and field the
    read_exif_data() key the value was read from (None for the filename and the
    file system). zoned sources carry their own zone.

    The QuickTime clock has two members because its digits are UTC by
    specification either way; the member records whether the file itself
    corroborated that (see docs/timestamp-fields.md, "A UTC-specified field is
    corroborated UTC only when the file shows it").
    """

    DATETIME_ORIGINAL_ZONED = ("DateTimeOriginal with timezone", "datetimeoriginal", False, "DateTimeOriginal", True)
    CREATION_DATE_ZONED = ("CreationDate with timezone", "creationdate", False, "CreationDate", True)
    CREATION_DATE_UTC = ("CreationDate with Z (UTC)", "creationdate", True, "CreationDate", False)
    MOVIE_HEADER_CORROBORATED = ("QuickTime CreateDate (corroborated UTC)", "moviecreatedate", True,
                                 MOVIE_HEADER_CREATE_DATE_TAG, False)
    FILENAME = ("filename", "filename", False, None, False)
    FILENAME_INFERRED = ("filename (infer mode)", "filename", False, None, False)
    MOVIE_HEADER_BY_SPEC = ("QuickTime CreateDate (UTC by spec)", "moviecreatedate", True,
                            MOVIE_HEADER_CREATE_DATE_TAG, False)
    DATETIME_ORIGINAL = ("DateTimeOriginal", "datetimeoriginal", False, "DateTimeOriginal", False)
    CREATION_DATE = ("CreationDate", "creationdate", False, "CreationDate", False)
    FILE_BIRTH = ("file birthtime", "file_birth", False, None, False)
    FILE_MTIME = ("file mtime", "file_mtime", False, None, False)
    NONE = ("no timestamps found", "no timestamps found", False, None, False)

    def __init__(self, display: str, token: str, is_utc: bool,
                 field: Optional[str], zoned: bool):
        self.display = display
        self.token = token
        self.is_utc = is_utc
        self.field = field
        self.zoned = zoned

    def __str__(self) -> str:
        return self.display


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


def normalize_exif_value(value: str) -> str:
    """Normalize EXIF value for comparison (handle timezone format differences)."""
    if not value:
        return ""
    return normalize_timezone_format(value)


# ---------------------------------------------------------------------------
# Filename timestamp parsing — generic date patterns
# ---------------------------------------------------------------------------

_PATTERNS_FILE = DATA_DIR / "filename-patterns.json"
_FILENAME_PATTERNS = [
    (re.compile(p["regex"]), p["name"])
    for p in json.loads(_PATTERNS_FILE.read_text())
]


def parse_filename_timestamp(file_path: str) -> tuple[Optional[str], Optional[str]]:
    """Extract timestamp from generic date patterns in filename.

    Returns:
        (timestamp_str in "YYYY:MM:DD HH:MM:SS" format, pattern_name) or (None, None)
    """
    base = os.path.splitext(os.path.basename(file_path))[0]

    for pattern_re, pattern_name in _FILENAME_PATTERNS:
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

    for pattern_re, pattern_name in _FILENAME_PATTERNS:
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
# Best timestamp
# ---------------------------------------------------------------------------

_MIN_ZONE_OFFSET = timedelta(hours=-12)
_MAX_ZONE_OFFSET = timedelta(hours=14)


def _is_legal_zone_offset(delta: timedelta) -> bool:
    """Whether a difference from UTC is one a real zone uses: -12:00 to +14:00,
    in quarter-hour steps."""
    if not _MIN_ZONE_OFFSET <= delta <= _MAX_ZONE_OFFSET:
        return False
    return delta.total_seconds() % 900 == 0


def _format_zone_offset(delta: timedelta) -> str:
    """Format a timedelta as a signed +HH:MM zone offset string."""
    total_minutes = int(delta.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    return f"{sign}{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def camera_zone_offset(
    quicktime_timestamp: Optional[str], filename_timestamp: Optional[str]
) -> Optional[str]:
    """The camera's own zone setting at shoot time, when discoverable.

    QuickTime dates are UTC by specification; the filename is the camera's own local
    reading. When their difference is a legal zone offset, that difference IS the zone
    the camera's clock was set to — independent of whether the QuickTime date ends up
    winning get_best_timestamp()'s priority race. Returns None when either timestamp is
    missing or the delta isn't a legal zone offset.
    """
    if not (quicktime_timestamp and filename_timestamp):
        return None
    try:
        quicktime = datetime.strptime(quicktime_timestamp, "%Y:%m:%d %H:%M:%S")
        local = datetime.strptime(filename_timestamp, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None

    delta = local - quicktime
    if delta == timedelta(0):
        # Identical values cannot separate a camera at UTC+0 from one writing local
        # time into a field defined as UTC.
        return None
    if not _is_legal_zone_offset(delta):
        return None
    return _format_zone_offset(delta)


def _is_corroborated_utc(utc_timestamp: str, filename_timestamp: Optional[str]) -> bool:
    """Whether the file corroborates that a UTC-specified field really holds UTC.

    The field is UTC by specification, but not every device honours that and a camera
    clock can simply be wrong. The filename is the camera's own local reading, so a
    legal zone offset between the two is the corroboration.
    """
    return camera_zone_offset(utc_timestamp, filename_timestamp) is not None


def _movie_header_timestamp(exif_data: Dict[str, str]) -> str:
    """Normalize QuickTime:CreateDate (mvhd) to 'YYYY:MM:DD HH:MM:SS', or '' if unusable."""
    movie_header_date = exif_data.get(MOVIE_HEADER_CREATE_DATE_TAG, "")
    if not (movie_header_date and re.search(r'[0-9]', movie_header_date)):
        return ""
    candidate = re.sub(
        r'([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}).*', r'\1',
        movie_header_date)
    return candidate if is_valid_timestamp(candidate) else ""


_TIMESTAMP_DIGITS = re.compile(r'([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}).*')
_TRAILING_ZONE = re.compile(r'[+-]\d{2}:?\d{2}$')

Candidate = Tuple[str, TimestampSource]


@dataclass(frozen=True)
class _RankingInputs:
    """Everything a ranking rule may look at, read once per file."""
    file_path: str
    exif: Dict[str, str]
    filename_timestamp: Optional[str]
    movie_timestamp: str
    timezone_offset: Optional[str]

    @property
    def basename(self) -> str:
        return os.path.basename(self.file_path)


def _digits(value: str) -> str:
    """The YYYY:MM:DD HH:MM:SS part of a tag value, dropping any zone suffix."""
    return _TIMESTAMP_DIGITS.sub(r'\1', value)


def _datetime_original_zoned(inputs: _RankingInputs) -> Optional[Candidate]:
    value = inputs.exif.get("DateTimeOriginal", "")
    if value and _TRAILING_ZONE.search(value):
        return _digits(value), TimestampSource.DATETIME_ORIGINAL_ZONED
    return None


def _creation_date_zoned(inputs: _RankingInputs) -> Optional[Candidate]:
    value = inputs.exif.get("CreationDate", "")
    if value and _TRAILING_ZONE.search(value):
        return _digits(value), TimestampSource.CREATION_DATE_ZONED
    return None


def _creation_date_utc(inputs: _RankingInputs) -> Optional[Candidate]:
    """Keys:CreationDate with a Z marker — UTC, so it needs a declared zone."""
    value = inputs.exif.get("CreationDate", "")
    if value and value.endswith('Z') and inputs.timezone_offset:
        timestamp = value[:-1].strip()
        if re.match(r'[0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}', timestamp):
            return timestamp, TimestampSource.CREATION_DATE_UTC
    return None


def _movie_header_corroborated(inputs: _RankingInputs) -> Optional[Candidate]:
    """A UTC clock value the filename corroborates.

    A camera left on the previous country's time writes a filename that is wrong
    for where it was shot; the UTC value survives that, so it wins where the two
    contradict each other. Without a declared timezone there is nothing to
    convert UTC into.
    """
    if inputs.timezone_offset and _is_corroborated_utc(inputs.movie_timestamp, inputs.filename_timestamp):
        return inputs.movie_timestamp, TimestampSource.MOVIE_HEADER_CORROBORATED
    return None


def _camera_filename(inputs: _RankingInputs) -> Optional[Candidate]:
    """The filename digits, for the camera patterns VID/IMG/LRV/DJI."""
    if inputs.filename_timestamp and (
            re.match(r'^(VID|LRV|IMG)_[0-9]{8}_[0-9]{6}', inputs.basename)
            or re.match(r'^DJI_[0-9]{14}_', inputs.basename)):
        return inputs.filename_timestamp, TimestampSource.FILENAME
    return None


def _movie_header_by_spec(inputs: _RankingInputs) -> Optional[Candidate]:
    """A UTC-specified clock value with nothing to corroborate it.

    Still ranks above the bare tags below: those are naive by definition, whereas
    this field at least has a specification saying what its digits mean.
    """
    if inputs.movie_timestamp:
        return inputs.movie_timestamp, TimestampSource.MOVIE_HEADER_BY_SPEC
    return None


def _datetime_original_bare(inputs: _RankingInputs) -> Optional[Candidate]:
    value = inputs.exif.get("DateTimeOriginal", "")
    if value and re.search(r'[0-9]', value):
        return _digits(value), TimestampSource.DATETIME_ORIGINAL
    return None


def _creation_date_bare(inputs: _RankingInputs) -> Optional[Candidate]:
    """CreationDate without a zone and without a Z marker — naive, the same tier
    as a bare DateTimeOriginal. No device is known to write this shape bare (see
    docs/timestamp-fields.md ranking row 7)."""
    value = inputs.exif.get("CreationDate", "")
    if value and not value.endswith('Z') and re.search(r'[0-9]', value):
        return _digits(value), TimestampSource.CREATION_DATE
    return None


def _file_times(inputs: _RankingInputs) -> Optional[Candidate]:
    """File birth time where the platform has one, else modification time."""
    try:
        st = os.stat(inputs.file_path)
    except OSError:
        return None
    birthtime = getattr(st, "st_birthtime", None)
    if birthtime is not None:
        return datetime.fromtimestamp(birthtime).strftime('%Y:%m:%d %H:%M:%S'), TimestampSource.FILE_BIRTH
    return datetime.fromtimestamp(st.st_mtime).strftime('%Y:%m:%d %H:%M:%S'), TimestampSource.FILE_MTIME


# The ranking in docs/timestamp-fields.md, first match wins. Adding a source means
# one rule here and one TimestampSource member.
RANKING: List[Callable[[_RankingInputs], Optional[Candidate]]] = [
    _datetime_original_zoned,
    _creation_date_zoned,
    _creation_date_utc,
    _movie_header_corroborated,
    _camera_filename,
    _movie_header_by_spec,
    _datetime_original_bare,
    _creation_date_bare,
    _file_times,
]


# ---------------------------------------------------------------------------
# FileReading — the one per-file result every consumer takes its facts from
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LocalTime:
    """A file's time on the wall clock where it was shot, as the hierarchy gives it.

    timestamp and source are the ranking's winner. time is that winner as an aware
    datetime in offset's zone, or None where nothing gives the digits a zone (a
    naive or UTC source with no declared timezone). text is how the time is
    stored: the tag's own value for a zoned tag left as it is, else time with its
    offset. declared says whether offset came from --timezone rather than from the
    file's own tag.
    """
    timestamp: Optional[str]
    source: TimestampSource
    offset: Optional[str] = None
    time: Optional[datetime] = None
    text: str = ""
    declared: bool = False


def _zoned_text(dt: datetime) -> str:
    return ensure_colon_tz(dt.strftime("%Y:%m:%d %H:%M:%S%z"))


@dataclass(frozen=True)
class FileReading:
    """Everything the hierarchy derives from one file's cached exiftool read.

    exif is the read itself (read_exif_data()). filename_timestamp is the
    filename's digits, movie_timestamp the movie header clock, both as
    'YYYY:MM:DD HH:MM:SS' or empty. The rest is derived here and nowhere else.
    """
    file_path: str
    exif: Dict[str, str]
    filename_timestamp: Optional[str]
    filename_pattern: Optional[str]
    movie_timestamp: str

    @property
    def basename(self) -> str:
        return os.path.basename(self.file_path)

    @property
    def camera_zone(self) -> Optional[str]:
        """The camera's zone setting, where the UTC clock and the filename show it
        (camera_zone_offset()), whatever source wins the ranking."""
        return camera_zone_offset(self.movie_timestamp, self.filename_timestamp)

    @property
    def tagged_zone(self) -> Optional[str]:
        """The zone a zoned tag gives the file ('+HH:MM'), or None: the winning
        source's zone where that source is a zoned tag, which rank first whatever
        timezone is declared."""
        timestamp, source = self.best()
        if not (timestamp and source.zoned and source.field):
            return None
        return trailing_zone(self.exif.get(source.field, ""))

    def best(self, timezone_offset: Optional[str] = None) -> Tuple[Optional[str], TimestampSource]:
        """The file's best timestamp and the source it came from, per RANKING."""
        inputs = _RankingInputs(
            file_path=self.file_path,
            exif=self.exif,
            filename_timestamp=self.filename_timestamp,
            movie_timestamp=self.movie_timestamp,
            timezone_offset=timezone_offset,
        )
        for rule in RANKING:
            candidate = rule(inputs)
            if candidate is not None:
                return candidate
        return None, TimestampSource.NONE

    def declared_offset(self, timezone_spec: Optional[str]) -> Optional[str]:
        """The offset timezone_spec gives this file: a zone name resolves against
        the file's own timestamp, so each file gets the offset in effect when it
        was shot."""
        if not timezone_spec:
            return None
        timestamp, source = self.best(timezone_spec)
        return resolve_timezone_offset(timezone_spec, timestamp, source.is_utc)

    def local_time(self, timezone_spec: Optional[str] = None,
                   infer_from_filename: bool = False) -> LocalTime:
        """The file's wall-clock time where it was shot.

        A zoned tag keeps its instant, re-expressed in the declared zone when one
        is given; a UTC source is expressed in the declared zone; a naive source's
        digits are taken as local time in it. infer_from_filename takes the
        filename's digits in the declared zone whatever else the file holds.
        """
        if infer_from_filename:
            if not timezone_spec:
                raise ValueError("--infer-from-filename requires --timezone to be specified")
            if not self.filename_timestamp:
                raise ValueError("--infer-from-filename specified but filename has no parseable date")
            offset = resolve_timezone_offset(timezone_spec, self.filename_timestamp)
            text = f"{self.filename_timestamp}{offset}"
            return LocalTime(self.filename_timestamp, TimestampSource.FILENAME_INFERRED,
                             offset, parse_datetime_original(text), text, declared=True)

        timestamp, source = self.best(timezone_spec)
        offset = resolve_timezone_offset(timezone_spec, timestamp, timestamp_is_utc=source.is_utc)
        if not timestamp:
            return LocalTime(timestamp, source, offset)

        if source.zoned and source.field:
            raw_value = self.exif.get(source.field, "")
            embedded = parse_datetime_original(raw_value) if raw_value else None
            if not embedded:
                return LocalTime(timestamp, source, offset, None, raw_value)
            if timezone_spec:
                # The zoned tag defines an instant; the embedded offset is a label
                # from the camera's zone setting, which goes stale across a flight.
                # --timezone declares where the footage was shot, so the instant is
                # expressed in that zone rather than passed through unchanged.
                utc_str = embedded.astimezone(timezone.utc).strftime("%Y:%m:%d %H:%M:%S")
                declared = resolve_timezone_offset(timezone_spec, utc_str, timestamp_is_utc=True)
                declared_tz = tzinfo_from_offset(declared)
                if declared and declared_tz is not None:
                    converted = embedded.astimezone(declared_tz)
                    return LocalTime(timestamp, source, declared, converted,
                                     converted.strftime("%Y:%m:%d %H:%M:%S") + declared, declared=True)
            return LocalTime(timestamp, source, offset, embedded, raw_value)

        if source is TimestampSource.DATETIME_ORIGINAL and not offset:
            raw_value = self.exif.get("DateTimeOriginal", "")
            return LocalTime(timestamp, source, offset,
                             parse_datetime_original(raw_value) if raw_value else None, raw_value)

        local_tz = tzinfo_from_offset(offset)
        if local_tz is None:
            return LocalTime(timestamp, source, offset)
        if source.is_utc:
            # UTC digits are expressed in the declared zone: same instant, new label.
            utc_dt = datetime.strptime(timestamp, "%Y:%m:%d %H:%M:%S").replace(tzinfo=timezone.utc)
            text = utc_dt.astimezone(local_tz).strftime("%Y:%m:%d %H:%M:%S") + offset
        else:
            text = f"{timestamp}{offset}"
        return LocalTime(timestamp, source, offset, parse_datetime_original(text), text, declared=True)


def read_file(file_path: str) -> FileReading:
    """The file's FileReading, from its one cached exiftool read."""
    exif = read_exif_data(file_path)
    filename_timestamp, filename_pattern = parse_filename_timestamp(file_path)
    return FileReading(
        file_path=file_path,
        exif=exif,
        filename_timestamp=filename_timestamp,
        filename_pattern=filename_pattern,
        movie_timestamp=_movie_header_timestamp(exif),
    )


def get_best_timestamp(
    file_path: str,
    timezone_offset: Optional[str] = None,
) -> Tuple[Optional[str], TimestampSource]:
    """The file's best timestamp and the source it came from, per RANKING."""
    return read_file(file_path).best(timezone_offset)


# ---------------------------------------------------------------------------
# TimestampReport — unified analysis
# ---------------------------------------------------------------------------

@dataclass
class TimestampReport:
    """Everything known about a file's available timestamps."""
    metadata_date: Optional[datetime]
    metadata_source: TimestampSource
    metadata_tz: Optional[str]

    filename_parseable: bool
    filename_date: Optional[datetime]
    filename_pattern: Optional[str]


def read_timestamp_sources(
    file_path: str,
    timezone_offset: Optional[str] = None,
) -> TimestampReport:
    """Analyse a file and report all available timestamp sources."""
    reading = read_file(file_path)
    best_ts, source = reading.best(timezone_offset)

    metadata_date = None
    metadata_tz = reading.tagged_zone

    if best_ts:
        try:
            metadata_date = datetime.strptime(best_ts, '%Y:%m:%d %H:%M:%S')
        except ValueError:
            pass

    # Filename side
    fn_ts, fn_pattern = reading.filename_timestamp, reading.filename_pattern
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
