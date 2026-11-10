"""Reading a file for a correction: the time its winning source gives, in which
zone, and what a correction to that time would change.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from lib.fix_media_timestamp.clock_fields import needed_changes
from lib.timestamps.file_times import check_file_system_timestamps_need_update, get_file_system_timestamps
from lib.timestamps.sources import (
    TimestampSource,
    camera_zone_offset_for_file,
    extract_metadata_timezone,
    get_best_timestamp,
    parse_datetime_original,
    parse_filename_timestamp,
    read_exif_data,
    read_timestamp_sources,
    resolve_timezone_offset,
)

# Birth time is read, compared and written only on macOS, where it is what Final Cut
# Pro shows before import; elsewhere a correction leaves file times alone.
BIRTH_TIME_TRACKED = sys.platform == "darwin"

# How each source field is named to people: CreationDate is read from the Keys
# atom, which is the name a user sees in other tools.
FIELD_LABELS = {
    "DateTimeOriginal": "DateTimeOriginal",
    "CreationDate": "Keys:CreationDate",
}


def _timezone_from_offset(offset_str: str) -> Optional[timezone]:
    """Build a tzinfo from a +HH:MM / +HHMM offset string."""
    match = re.match(r'([+-])(\d{2}):?(\d{2})$', offset_str)
    if not match:
        return None
    sign, hours, minutes = match.groups()
    offset_seconds = int(hours) * 3600 + int(minutes) * 60
    if sign == '-':
        offset_seconds = -offset_seconds
    return timezone(timedelta(seconds=offset_seconds))


def get_all_timestamp_data(file_path: str, timezone_spec: Optional[str] = None, infer_from_filename: bool = False) -> dict:
    """Get all current timestamp data from file.

    timezone_spec is either a fixed +HHMM offset or an IANA zone name. A zone
    name resolves against this file's own timestamp, so a run spanning a DST
    changeover gives each file the offset that applied when it was shot.

    When infer_from_filename=True:
    - Requires timezone_spec to be provided
    - Uses filename timestamp with provided timezone as source of truth
    - Ignores existing EXIF timestamps
    """
    data: Dict[str, Any] = {
        "file_path": file_path,
        "exif": read_exif_data(file_path),
        "file_system": get_file_system_timestamps(file_path) if BIRTH_TIME_TRACKED else {"birth": "", "modify": ""},
        "datetime_original_str": "",
        "datetime_original": None,
        "timestamp_source": TimestampSource.NONE,
        "timezone_source": "",
        "timezone_offset": None,
        "camera_zone_offset": camera_zone_offset_for_file(file_path),
    }

    if infer_from_filename:
        if not timezone_spec:
            raise ValueError("--infer-from-filename requires --timezone to be specified")
        report = read_timestamp_sources(file_path, timezone_spec)
        if not report.filename_parseable:
            raise ValueError("--infer-from-filename specified but filename has no parseable date")
        fn_ts, _ = parse_filename_timestamp(file_path)
        timezone_offset = resolve_timezone_offset(timezone_spec, fn_ts)
        data["timezone_offset"] = timezone_offset
        datetime_with_tz = f"{fn_ts}{timezone_offset}"
        data["datetime_original_str"] = datetime_with_tz
        data["datetime_original"] = parse_datetime_original(datetime_with_tz)
        data["timestamp_source"] = TimestampSource.FILENAME_INFERRED
        data["timezone_source"] = f"--timezone flag ({timezone_offset})"
        return data

    best_timestamp, source = get_best_timestamp(file_path, timezone_spec)
    data["timestamp_source"] = source

    timezone_offset = resolve_timezone_offset(
        timezone_spec, best_timestamp, timestamp_is_utc=source.is_utc,
    )
    data["timezone_offset"] = timezone_offset

    if best_timestamp:
        if source.zoned and source.field:
            raw_value = data["exif"].get(source.field, "")
            data["timezone_source"] = f"{FIELD_LABELS[source.field]} metadata"
            data["datetime_original_str"] = raw_value
            embedded = parse_datetime_original(raw_value) if raw_value else None
            if embedded:
                data["datetime_original"] = embedded
                if timezone_spec:
                    # The zoned tag defines an instant; the embedded offset is a label
                    # from the camera's zone setting, which goes stale across a flight.
                    # --timezone declares where the footage was shot, so the instant is
                    # expressed in that zone rather than passed through unchanged.
                    utc_str = embedded.astimezone(timezone.utc).strftime("%Y:%m:%d %H:%M:%S")
                    declared_offset = resolve_timezone_offset(timezone_spec, utc_str, timestamp_is_utc=True)
                    declared_tz = _timezone_from_offset(declared_offset) if declared_offset else None
                    if declared_offset and declared_tz is not None:
                        converted = embedded.astimezone(declared_tz)
                        data["timezone_offset"] = declared_offset
                        data["datetime_original"] = converted
                        data["datetime_original_str"] = converted.strftime("%Y:%m:%d %H:%M:%S") + declared_offset
                        data["timezone_source"] = f"--timezone flag ({declared_offset})"
        elif source is TimestampSource.DATETIME_ORIGINAL and not timezone_offset:
            data["datetime_original_str"] = data["exif"].get("DateTimeOriginal", "")
            data["timezone_source"] = "DateTimeOriginal metadata"
            if data["datetime_original_str"]:
                data["datetime_original"] = parse_datetime_original(data["datetime_original_str"])
        elif source.is_utc:
            # UTC digits are expressed in the declared zone: same instant, new label.
            local_tz = _timezone_from_offset(timezone_offset) if timezone_offset else None
            if timezone_offset and local_tz is not None:
                utc_dt = datetime.strptime(best_timestamp, "%Y:%m:%d %H:%M:%S").replace(tzinfo=timezone.utc)
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


def determine_needed_changes(file_path: str, datetime_original: datetime, preserve_wallclock: bool = False,
                             write_datetime_original: bool = False,
                             write_zone: bool = False) -> dict:
    """needed_changes() for a file, reading its fields and birth time.

    Args:
        file_path: Path to the media file
        datetime_original: datetime object with timezone info
        preserve_wallclock: If True, preserve wall-clock shooting time for birth time
        write_datetime_original: If True, DateTimeOriginal is a field this correction owns
        write_zone: If True, OffsetTimeOriginal is owned even where DateTimeOriginal is not
    """
    exif = read_exif_data(file_path)
    birth_time_stale = (
        check_file_system_timestamps_need_update(file_path, datetime_original, preserve_wallclock)
        if BIRTH_TIME_TRACKED else False
    )
    return needed_changes(exif, datetime_original, birth_time_stale,
                          write_datetime_original, write_zone)


@dataclass(frozen=True)
class CorrectionOptions:
    """How a correction was asked for.

    extra_write_fields are other steps' field writes, sent in this correction's
    exiftool call so the file is rewritten once. They are written even when the
    timestamps need no change.

    record_provenance makes a missing provenance record a reason to write on its
    own, for a caller that records provenance on every file it moves. Without it
    the record rides only on a write the file needed anyway.
    """
    apply: bool = True
    timezone_spec: Optional[str] = None
    infer_from_filename: bool = False
    preserve_wallclock: bool = False
    time_offset_seconds: Optional[int] = None
    force_timezone: bool = False
    extra_write_fields: Dict[str, str] = dataclass_field(default_factory=dict)
    record_provenance: bool = False

    @property
    def moves_time(self) -> bool:
        """Whether --time-offset moves the actual time, rather than only relabelling it."""
        return self.time_offset_seconds is not None and self.time_offset_seconds != 0


@dataclass(frozen=True)
class CurrentTimestamps:
    """What a file holds now, as far as a correction is concerned.

    data is get_all_timestamp_data()'s reading: the fields, the winning source and
    the time it gives. detected_tz is the zone the file's metadata carries.
    """
    file_path: str
    data: Dict[str, Any]
    detected_tz: Optional[str] = None
    birth_time_tracked: bool = BIRTH_TIME_TRACKED


def read_current(file_path: str, opts: CorrectionOptions) -> CurrentTimestamps:
    """Read everything plan_correction() needs from the file (one metadata read)."""
    detected_tz = extract_metadata_timezone(file_path) or None
    data = get_all_timestamp_data(file_path, opts.timezone_spec, opts.infer_from_filename)
    return CurrentTimestamps(file_path=file_path, data=data, detected_tz=detected_tz)
