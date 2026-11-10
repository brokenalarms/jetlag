"""The clock fields a correction owns, and how a file's stored values compare.

CLOCK_FIELDS drives both the comparison against a file's stored values and the
write; needed_changes() is that comparison for a correction to one time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict

from lib.timestamps.sources import MOVIE_HEADER_CREATE_DATE_TAG, ensure_colon_tz, normalize_exif_value, trailing_zone


@dataclass(frozen=True)
class ClockField:
    """A metadata clock field a correction owns.

    write_tag is what exiftool is given; read_key is what the value comes back
    under in read_exif_data(). quicktime fields hold a raw UTC instant and exist
    only in a QuickTime container; the rest hold zoned local time, except a
    holds_zone field, whose value is that zone on its own.
    container_only marks the fields that exist only in a QuickTime container:
    exiftool refuses to write them to a still (verified on JPEG and HEIC), so
    targeting them there would leave every still permanently reporting a stale
    field it can never hold.
    proves_container marks the fields whose presence identifies the file as a
    QuickTime container — bare `CreateDate` is also an EXIF stills tag holding
    local time, so it can never be the evidence.
    owned_with_datetime_original marks the fields a correction owns only when it
    owns DateTimeOriginal: they describe that one value, so they are written with
    it or not at all.
    """
    write_tag: str
    read_key: str
    quicktime: bool
    container_only: bool = False
    proves_container: bool = False
    owned_with_datetime_original: bool = False
    holds_zone: bool = False


# Every metadata clock field a correction owns, per the "jetlag writes" column of
# docs/timestamp-fields.md. This one table drives both the comparison against a
# file's stored values and the write, so a correction can never write a subset:
# a stale movie header cannot survive a run that found the track atoms correct.
CLOCK_FIELDS = [
    ClockField("DateTimeOriginal", "DateTimeOriginal", quicktime=False,
               owned_with_datetime_original=True),
    ClockField("OffsetTimeOriginal", "OffsetTimeOriginal", quicktime=False,
               owned_with_datetime_original=True, holds_zone=True),
    ClockField("Keys:CreationDate", "CreationDate", quicktime=False, container_only=True),
    ClockField("QuickTime:CreateDate", MOVIE_HEADER_CREATE_DATE_TAG, quicktime=True,
               container_only=True, proves_container=True),
    ClockField("QuickTime:MediaCreateDate", "MediaCreateDate", quicktime=True,
               container_only=True, proves_container=True),
    ClockField("QuickTime:TrackCreateDate", "TrackCreateDate", quicktime=True,
               container_only=True, proves_container=True),
]


def is_quicktime_container(exif: Dict[str, str]) -> bool:
    """Whether a file's clock fields come from a QuickTime container."""
    return any(exif.get(field.read_key) for field in CLOCK_FIELDS if field.proves_container)


def clock_field_targets(exif: Dict[str, str], datetime_original: datetime,
                        write_datetime_original: bool = False,
                        write_zone: bool = False) -> Dict[str, str]:
    """The value every clock field a correction owns must end up holding.

    Zoned local time for DateTimeOriginal and Keys:CreationDate; that value's zone
    alone for OffsetTimeOriginal; the same instant as raw UTC for the QuickTime
    atoms. Stills get no container-only entries. DateTimeOriginal and the zone that
    completes it are owned only when the caller has decided to write it — an
    existing tag is otherwise the source, not a target. write_zone additionally
    owns the zone alone, for a bare DateTimeOriginal that stays as it is but is
    being labelled with a declared zone.

    OffsetTimeOriginal is targeted whatever the container holds it: a still's
    binary EXIF DateTimeOriginal is 19 characters, so the offset tag is the only
    place its zone can live, while on a video exiftool keeps the zone inline in
    XMP and drops the offset tag. One uniform write is right for both.
    """
    zoned = ensure_colon_tz(datetime_original.strftime('%Y:%m:%d %H:%M:%S%z'))
    zone = ensure_colon_tz(datetime_original.strftime('%z'))
    utc = datetime_original.astimezone(timezone.utc).strftime("%Y:%m:%d %H:%M:%S")
    container = is_quicktime_container(exif)

    targets = {}
    for field in CLOCK_FIELDS:
        if field.container_only and not container:
            continue
        owned = write_datetime_original or (write_zone and field.holds_zone)
        if field.owned_with_datetime_original and not owned:
            continue
        if field.quicktime:
            targets[field.write_tag] = utc
        elif field.holds_zone:
            targets[field.write_tag] = zone
        else:
            targets[field.write_tag] = zoned
    return targets


def _utc_clock_differs(current: str, target: str) -> bool:
    """Whether a stored UTC clock value differs from the expected one.

    A one second tolerance absorbs rounding; an unparseable value counts as stale.
    """
    try:
        current_dt = datetime.strptime(current, "%Y:%m:%d %H:%M:%S")
        target_dt = datetime.strptime(target, "%Y:%m:%d %H:%M:%S")
        return abs((current_dt - target_dt).total_seconds()) > 1
    except ValueError:
        return True


def stored_zone(exif: Dict[str, str]) -> str:
    """The zone the file already conveys for DateTimeOriginal's digits, as ±HH:MM.

    The raw OffsetTimeOriginal is the whole answer where the file has one — not
    the value _complete_datetime_original() joins into DateTimeOriginal, which
    would report the zone as stored no matter what the offset tag holds. Where
    the tag cannot exist, the zone rides inline in DateTimeOriginal instead
    (XMP on a video), and it is that inline zone the file conveys.
    """
    offset = ensure_colon_tz((exif.get("OffsetTimeOriginal") or "").strip())
    if offset:
        return offset

    inline = trailing_zone(exif.get("DateTimeOriginal", ""))
    if not inline:
        return ""
    return "+00:00" if inline == "Z" else inline


def stale_clock_fields(exif: Dict[str, str], targets: Dict[str, str]) -> list:
    """The write tags in targets whose stored value is missing or differs."""
    stale = []
    for field in CLOCK_FIELDS:
        if field.write_tag not in targets:
            continue
        target = targets[field.write_tag]
        if field.quicktime:
            differs = _utc_clock_differs(exif.get(field.read_key, ""), target)
        elif field.holds_zone:
            differs = stored_zone(exif) != target
        else:
            differs = (normalize_exif_value(exif.get(field.read_key, ""))
                       != normalize_exif_value(target))
        if differs:
            stale.append(field.write_tag)
    return stale


def missing_clock_fields(exif: Dict[str, str], stale: list) -> list:
    """The stale write tags the file holds no value for at all.

    A missing field is not evidence against the file's time: a camera that never
    writes Keys:CreationDate has nothing wrong with it, only something to add.
    """
    stored = {
        field.write_tag: stored_zone(exif) if field.holds_zone else exif.get(field.read_key, "")
        for field in CLOCK_FIELDS
    }
    return [tag for tag in stale if not stored.get(tag)]


def needed_changes(exif: Dict[str, str], datetime_original: datetime, birth_time_stale: bool,
                   write_datetime_original: bool = False, write_zone: bool = False) -> dict:
    """What a correction to datetime_original must change, from the fields already read.

    Returns the correction's target value per clock field, the write tags whose
    stored value does not already match, those of them the file holds no value
    for, and whether the birth time is stale.
    """
    targets = clock_field_targets(exif, datetime_original, write_datetime_original, write_zone)
    stale = stale_clock_fields(exif, targets)
    return {
        "clock_targets": targets,
        "stale_clock_fields": stale,
        "missing_clock_fields": missing_clock_fields(exif, stale),
        "file_timestamps": birth_time_stale,
    }
