"""Planning a correction: everything it will say and write, worked out from what
the file holds now before either happens. Pure — no file is read or written here.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from lib.fix_media_timestamp.clock_fields import is_quicktime_container, needed_changes, stored_zone
from lib.fix_media_timestamp.read import CorrectionOptions, CurrentTimestamps
from lib.timestamps.file_times import birth_time_in_future, birth_time_needs_update, get_expected_file_system_time
from lib.timestamps.provenance import provenance_field_args
from lib.timestamps.sources import MOVIE_HEADER_CREATE_DATE_TAG, TimestampSource, normalize_timezone_format


@dataclass
class TimestampFixResult:
    file: str
    timestamp_action: str  # "fixed" | "would_fix" | "added" | "would_add" | "no_change" | "error"
    original_time: Optional[str] = None
    corrected_time: Optional[str] = None
    timestamp_source: Optional[str] = None
    correction_mode: Optional[str] = None
    timezone: Optional[str] = None
    time_offset_seconds: Optional[int] = None
    time_offset_display: Optional[str] = None
    original_epoch: Optional[float] = None
    corrected_epoch: Optional[float] = None
    requires_force_timezone: Optional[bool] = None
    camera_zone_offset: Optional[str] = None
    stale_fields: list = dataclass_field(default_factory=list)
    stale_file_times: list = dataclass_field(default_factory=list)
    error: Optional[str] = None
    reason: Optional[str] = None


def machine_original_time(current_data: dict) -> str:
    """The winning source's stored timestamp, carrying whether it is UTC.

    A UTC clock stores bare digits, so the value alone cannot be told apart from a
    naive local one: a consumer comparing it against the zoned corrected_time reads
    a relabel as a shift. UTC sources are therefore emitted with a trailing Z -
    "these digits are UTC" - which is a different claim from a +00:00 offset
    ("local time in a zero-offset zone"). Naive sources - a filename, a bare
    tag - have no zone, and stay bare rather than claiming one.
    """
    return _apply_source_zone(_stored_original_time(current_data),
                              current_data.get("timestamp_source", TimestampSource.NONE))


def _apply_source_zone(value: str, source: TimestampSource) -> str:
    """Mark a UTC source's stored value as UTC; leave any other source alone."""
    if not value or not source.is_utc:
        return value
    if value.endswith("Z") or re.search(r'[+-]\d{2}:?\d{2}$', value):
        return value
    return f"{value}Z"


def _stored_original_time(current_data: dict) -> str:
    """The EXIF field value the timestamp source was read from.

    Falls back through the common fields when the source-specific one is empty.
    """
    exif = current_data.get("exif", {})
    source = current_data.get("timestamp_source", TimestampSource.NONE)

    if source.field and exif.get(source.field):
        return exif[source.field]

    # Fallback: first non-empty common timestamp field
    for field in ["DateTimeOriginal", "CreationDate", MOVIE_HEADER_CREATE_DATE_TAG, "CreateDate"]:
        val = exif.get(field, "")
        if val:
            return val
    return ""


def format_offset_display(seconds: int) -> str:
    """Format a time offset in seconds to human-readable display.

    Examples: +1d 2h 3m 4s, -0d 1h 30m 0s, +0d 0h 5m 0s
    """
    sign = "+" if seconds >= 0 else "-"
    total = abs(seconds)
    days = total // 86400
    hours = (total % 86400) // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    return f"{sign}{days}d {hours}h {minutes}m {secs}s"


# Why a correction cannot be made at all.
REFUSED_WITHOUT_FORCE = "refused_without_force"  # applying would relabel a zoned file unconfirmed
ZONE_NEEDED = "zone_needed"                      # a CreateDate, no DateTimeOriginal, no --timezone
NO_TIMESTAMP = "no_timestamp"                    # nothing to correct from
BIRTH_TIME_IN_FUTURE = "birth_time_in_future"    # the corrected birth time is later than now


@dataclass(frozen=True)
class CorrectionPlan:
    """Everything a correction will say and write, worked out before either happens.

    problem names why there is nothing to correct (None when there is). original
    is the time the winning source gives; corrected is it after --time-offset.
    """
    current: CurrentTimestamps
    opts: CorrectionOptions
    requires_force_timezone: bool = False
    problem: Optional[str] = None
    original: Optional[datetime] = None
    corrected: Optional[datetime] = None
    corrected_str: str = ""
    write_datetime_original: bool = False
    changes: Dict[str, Any] = dataclass_field(default_factory=dict)
    birth_time: Optional[Dict[str, Any]] = None
    provenance_args: list = dataclass_field(default_factory=list)
    correction_args: list = dataclass_field(default_factory=list)
    extra_args: list = dataclass_field(default_factory=list)
    file_time_args: list = dataclass_field(default_factory=list)

    @property
    def filename(self) -> str:
        return os.path.basename(self.current.file_path)

    @property
    def has_changes(self) -> bool:
        return bool(self.changes.get("stale_clock_fields")) or bool(self.changes.get("file_timestamps"))

    @property
    def correction_mode(self) -> str:
        return "time" if self.opts.moves_time else "timezone"

    @property
    def only_adds_fields(self) -> bool:
        """Writing only into fields the file left empty fills in what it never had;
        any stored value or file time that disagrees, or a moved time, is a fix."""
        return (
            self.correction_mode == "timezone"
            and not self.changes["file_timestamps"]
            and len(self.changes["missing_clock_fields"]) == len(self.changes["stale_clock_fields"])
        )

    @property
    def writes(self) -> bool:
        """Whether applying this plan sends a write to exiftool's process."""
        return (self.problem is None and self.opts.apply
                and (self.has_changes or bool(self.opts.extra_write_fields)
                     or (self.opts.record_provenance and bool(self.provenance_args))))

    def result(self, action: str, error: Optional[str] = None,
               reason: Optional[str] = None) -> TimestampFixResult:
        """The machine-readable result of this plan ending in action."""
        data = self.current.data
        offset = self.opts.time_offset_seconds if self.opts.moves_time else None
        return TimestampFixResult(
            file=self.filename,
            timestamp_action=action,
            original_time=machine_original_time(data),
            corrected_time=self.corrected_str,
            stale_fields=self.changes.get("stale_clock_fields", []),
            stale_file_times=["FileCreateDate"] if self.changes.get("file_timestamps") else [],
            timestamp_source=data["timestamp_source"].token,
            correction_mode=self.correction_mode,
            timezone=self.current.detected_tz,
            time_offset_seconds=offset,
            time_offset_display=format_offset_display(offset) if offset is not None else None,
            original_epoch=self.original.timestamp() if self.original else None,
            corrected_epoch=self.corrected.timestamp() if self.corrected else None,
            requires_force_timezone=self.requires_force_timezone or None,
            camera_zone_offset=data.get("camera_zone_offset"),
            error=error,
            reason=reason,
        )


def plan_correction(current: CurrentTimestamps, opts: CorrectionOptions) -> CorrectionPlan:
    """Work out what correcting a file means, from what it holds now. Pure."""
    data = current.data
    exif = data["exif"]

    # --force-timezone is a confirmation gate, not arithmetic: relabelling a file whose
    # winning source already carries a zone must be explicitly confirmed. The corrected
    # value is the same instant either way — get_all_timestamp_data() already expressed
    # it in the declared zone. A dry run always previews the relabel; applying is what
    # the flag confirms.
    requires_force_timezone = False
    if opts.timezone_spec and not opts.infer_from_filename:
        source = data["timestamp_source"]
        declared_offset = data.get("timezone_offset")
        if (source.zoned and current.detected_tz and declared_offset
                and normalize_timezone_format(current.detected_tz) != normalize_timezone_format(declared_offset)):
            requires_force_timezone = not opts.force_timezone
    if requires_force_timezone and opts.apply:
        return CorrectionPlan(current, opts, requires_force_timezone=True,
                              problem=REFUSED_WITHOUT_FORCE)

    if not data["datetime_original"]:
        zone_needed = exif.get("CreateDate", "") and not opts.timezone_spec
        return CorrectionPlan(current, opts, requires_force_timezone=requires_force_timezone,
                              problem=ZONE_NEEDED if zone_needed else NO_TIMESTAMP)

    original = data["datetime_original"]
    corrected, corrected_str = original, data["datetime_original_str"]
    if opts.moves_time:
        corrected = original + timedelta(seconds=opts.time_offset_seconds or 0)
        corrected_str = re.sub(r'([+-]\d{2})(\d{2})$', r'\1:\2', corrected.strftime('%Y:%m:%d %H:%M:%S%z'))

    # DateTimeOriginal is a field this correction owns when:
    # 1. It's missing and we have timezone info, OR
    # 2. infer_from_filename is set (filename is the source of truth, DTO may be wrong/missing)
    # 3. force_timezone is set (the confirmed relabel must reach the stored tag)
    write_datetime_original = bool(
        (not exif.get("DateTimeOriginal") and corrected_str) or
        (opts.infer_from_filename and corrected_str) or
        (opts.force_timezone and corrected_str)
    )

    # A still's bare DateTimeOriginal labelled by --timezone keeps its digits but
    # needs the declared zone stored beside it; a video carries its zone elsewhere.
    write_zone = bool(
        exif.get("DateTimeOriginal")
        and not is_quicktime_container(exif)
        and not stored_zone(exif)
        and data.get("timezone_source", "").startswith("--timezone flag")
    )

    current_birth = data["file_system"].get("birth", "")
    birth_time_stale = current.birth_time_tracked and birth_time_needs_update(
        current_birth, corrected, opts.preserve_wallclock)
    changes = needed_changes(exif, corrected, birth_time_stale, write_datetime_original, write_zone)

    expected_birth = get_expected_file_system_time(corrected, preserve_wallclock=opts.preserve_wallclock)
    if current.birth_time_tracked and birth_time_in_future(expected_birth, current.read_at):
        return CorrectionPlan(current, opts, requires_force_timezone=requires_force_timezone,
                              problem=BIRTH_TIME_IN_FUTURE, original=original, corrected=corrected,
                              corrected_str=corrected_str,
                              birth_time={"expected_time": expected_birth})
    birth_time: Optional[Dict[str, Any]] = None
    if changes["file_timestamps"]:
        birth_time = {"expected_time": expected_birth, "current_birth": current_birth,
                      "birth_delta_seconds": None}
        try:
            expected_dt = datetime.strptime(expected_birth, '%Y:%m:%d %H:%M:%S')
            if current_birth:
                birth = datetime.strptime(current_birth, '%Y:%m:%d %H:%M:%S')
                birth_time["birth_delta_seconds"] = (expected_dt - birth).total_seconds()
        except ValueError:
            pass

    # Capture what the file held before jetlag touches it, in the same write as the
    # correction. A dry run writes nothing, so it records nothing.
    provenance_args = provenance_field_args(current.file_path, exif) if opts.apply else []
    # A correction owns the whole clock-field table, so one stale field rewrites
    # them all: a subset write is what let a stale movie header outlive a run that
    # found the track atoms correct.
    correction_args = [
        f"-{tag}={value}" for tag, value in changes["clock_targets"].items()
    ] if changes["stale_clock_fields"] else []
    extra_args = [f"-{tag}={value}" for tag, value in opts.extra_write_fields.items()]
    # Rewriting the file for any field resets its birth time, so the birth time rides
    # in the same exiftool call, which applies file system tags after the rewrite —
    # whether or not the correction found it stale.
    file_time_args = [f"-FileCreateDate={expected_birth}"] if current.birth_time_tracked and (
        changes["file_timestamps"] or provenance_args or correction_args or extra_args) else []

    return CorrectionPlan(
        current, opts,
        requires_force_timezone=requires_force_timezone,
        original=original,
        corrected=corrected,
        corrected_str=corrected_str,
        write_datetime_original=write_datetime_original,
        changes=changes,
        birth_time=birth_time,
        provenance_args=provenance_args,
        correction_args=correction_args,
        extra_args=extra_args,
        file_time_args=file_time_args,
    )
