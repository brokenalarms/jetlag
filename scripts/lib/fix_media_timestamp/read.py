"""Reading a file for a correction: the time its winning source gives, in which
zone, and what a correction to that time would change.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime
from typing import Any, Dict, Optional

from lib.fix_media_timestamp.clock_fields import needed_changes
from lib.timestamps.file_times import check_file_system_timestamps_need_update, get_file_system_timestamps
from lib.timestamps.sources import FileReading, read_exif_data, read_file

# Birth time is read, compared and written only on macOS, where it is what Final Cut
# Pro shows before import; elsewhere a correction leaves file times alone.
BIRTH_TIME_TRACKED = sys.platform == "darwin"

# How each source field is named to people: CreationDate is read from the Keys
# atom, which is the name a user sees in other tools.
FIELD_LABELS = {
    "DateTimeOriginal": "DateTimeOriginal",
    "CreationDate": "Keys:CreationDate",
}


def timestamp_data(reading: FileReading, timezone_spec: Optional[str] = None,
                   infer_from_filename: bool = False) -> dict:
    """A correction's view of one FileReading: its fields, the winning source and
    the wall-clock time it gives (FileReading.local_time()).

    timezone_spec is either a fixed +HHMM offset or an IANA zone name. A zone
    name resolves against this file's own timestamp, so a run spanning a DST
    changeover gives each file the offset that applied when it was shot.
    """
    local = reading.local_time(timezone_spec, infer_from_filename)
    if local.declared:
        timezone_source = f"--timezone flag ({local.offset})"
    elif local.text and local.source.field:
        timezone_source = f"{FIELD_LABELS[local.source.field]} metadata"
    else:
        timezone_source = ""
    file_path = reading.file_path
    return {
        "file_path": file_path,
        "exif": reading.exif,
        "file_system": get_file_system_timestamps(file_path) if BIRTH_TIME_TRACKED else {"birth": "", "modify": ""},
        "filename_timestamp": reading.filename_timestamp,
        "datetime_original_str": local.text,
        "datetime_original": local.time,
        "timestamp_source": local.source,
        "timezone_source": timezone_source,
        "timezone_offset": local.offset,
        "camera_zone_offset": reading.camera_zone,
    }


def get_all_timestamp_data(file_path: str, timezone_spec: Optional[str] = None, infer_from_filename: bool = False) -> dict:
    """timestamp_data() for a file, from its one cached read."""
    return timestamp_data(read_file(file_path), timezone_spec, infer_from_filename)


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
    the time it gives. detected_tz is the zone the file's metadata carries. read_at
    is when it was read, in local time: the "now" a planned birth time is held to.
    """
    file_path: str
    data: Dict[str, Any]
    detected_tz: Optional[str] = None
    birth_time_tracked: bool = BIRTH_TIME_TRACKED
    read_at: datetime = dataclass_field(default_factory=datetime.now)


def read_current(file_path: str, opts: CorrectionOptions) -> CurrentTimestamps:
    """Read everything plan_correction() needs from the file (one metadata read)."""
    reading = read_file(file_path)
    data = timestamp_data(reading, opts.timezone_spec, opts.infer_from_filename)
    return CurrentTimestamps(file_path=file_path, data=data, detected_tz=reading.tagged_zone)
