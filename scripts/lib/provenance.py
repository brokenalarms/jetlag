"""The provenance record: what a file held before jetlag first wrote to it.

Written in the same exiftool call as the timestamp correction (see
docs/specs/verify-card.md, "Provenance"), and read back by verification.
"""

from __future__ import annotations

import os
import sys
from typing import Dict

from lib.exiftool import exiftool
from lib.timestamp_source import (
    LEGACY_PROVENANCE_TAG,
    MOVIE_HEADER_CREATE_DATE_TAG,
    PRESERVED_FILENAME_TAG,
    is_valid_timestamp,
)


PROVENANCE_CLOCK_TAGS = {
    "DateTimeOriginal": "XMP-jetlag:OriginalDateTimeOriginal",
    MOVIE_HEADER_CREATE_DATE_TAG: "XMP-jetlag:OriginalCreateDate",
    "CreateDate": "XMP-jetlag:OriginalCreateDate",
    "MediaCreateDate": "XMP-jetlag:OriginalMediaCreateDate",
    "TrackCreateDate": "XMP-jetlag:OriginalTrackCreateDate",
    "CreationDate": "XMP-jetlag:OriginalCreationDate",
}


def read_provenance_record(file_path: str) -> Dict[str, str]:
    """Return the provenance properties stored in the file, keyed by tag name."""
    try:
        return exiftool.read_tags(file_path, [PRESERVED_FILENAME_TAG, "XMP-jetlag:all"])
    except Exception as e:
        print(f"Error reading provenance record: {e}", file=sys.stderr)
        return {}


def provenance_field_args(file_path: str, exif: Dict[str, str]) -> list:
    """Field args recording a file's clock fields and filename, or [] if already recorded.

    Written for recovery outside the app and never read back as a timestamp source:
    corrections always derive from the camera's own fields and the filename. A file
    that already carries a record is left untouched, so the record keeps describing
    the state before the first correction rather than the previous one's output.

    Built from the fields already read for the correction and returned as args rather
    than written here, so recording costs neither an extra read nor an extra write.
    """
    already_recorded = (
        exif.get(PRESERVED_FILENAME_TAG.split(":")[-1])
        or exif.get(LEGACY_PROVENANCE_TAG.split(":")[-1])
    )
    if already_recorded:
        return []

    # A still's bare CreateDate and a movie's header both record as OriginalCreateDate;
    # the movie header wins so an XMP CreateDate cannot stand in for it.
    recorded = {
        record_tag: exif[source]
        for source, record_tag in reversed(PROVENANCE_CLOCK_TAGS.items())
        if is_valid_timestamp(exif.get(source, ""))
    }
    clock_args = [f"-{record_tag}={value}" for record_tag, value in recorded.items()]
    return [f"-{PRESERVED_FILENAME_TAG}={os.path.basename(file_path)}"] + clock_args
