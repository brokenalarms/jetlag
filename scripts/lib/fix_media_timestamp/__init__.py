"""
fix-media-timestamp: correct one photo or video file's timestamps.

Works out declaratively what every clock field and the file's birth time should
hold, describes the change on stderr, and applies it in one exiftool write. The
rules are in docs/timestamp-fields.md. A correction is four steps, one module each:

- read:         read_current(), what the file holds now (one metadata read)
- plan:         plan_correction(), pure: what the correction says and writes
- describe:     describe_correction(), the change as the user reads it
- apply:        apply_correction(), at most one write, and the result
- clock_fields: the table of fields a correction owns, and how stored values compare
"""

from __future__ import annotations

import sys
from typing import Dict, Optional

from lib.fix_media_timestamp.apply import apply_correction
from lib.fix_media_timestamp.describe import describe_correction
from lib.fix_media_timestamp.plan import (
    NO_TIMESTAMP, REFUSED_WITHOUT_FORCE, ZONE_NEEDED, CorrectionPlan, TimestampFixResult,
    plan_correction,
)
from lib.fix_media_timestamp.read import CorrectionOptions, CurrentTimestamps, read_current

__all__ = [
    "NO_TIMESTAMP", "REFUSED_WITHOUT_FORCE", "ZONE_NEEDED", "CorrectionOptions", "CorrectionPlan",
    "CurrentTimestamps", "TimestampFixResult", "apply_correction", "describe_correction",
    "fix_media_timestamps", "plan_correction", "read_current",
]


def fix_media_timestamps(file_path: str, apply: bool = True, timezone_spec: Optional[str] = None,
                         infer_from_filename: bool = False, preserve_wallclock: bool = False,
                         time_offset_seconds: Optional[int] = None, force_timezone: bool = False,
                         extra_write_fields: Optional[Dict[str, str]] = None,
                         record_provenance: bool = False) -> TimestampFixResult:
    """Fix media (photo/video) timestamps: read, plan, describe on stderr, apply.

    extra_write_fields are other steps' field writes, sent in this step's exiftool
    call so the file is rewritten once. They are written even when the timestamps
    need no change.

    record_provenance makes a missing provenance record a reason to write on its own,
    for a caller that records provenance on every file it moves. Without it the record
    rides only on a write the file needed anyway.

    Returns:
        TimestampFixResult with all machine-readable fields populated.
        The caller (main) serialises this to @@key=value via emit_result().
    """
    opts = CorrectionOptions(
        apply=apply,
        timezone_spec=timezone_spec,
        infer_from_filename=infer_from_filename,
        preserve_wallclock=preserve_wallclock,
        time_offset_seconds=time_offset_seconds,
        force_timezone=force_timezone,
        extra_write_fields=dict(extra_write_fields or {}),
        record_provenance=record_provenance,
    )
    plan = plan_correction(read_current(file_path, opts), opts)
    print(describe_correction(plan), file=sys.stderr)
    return apply_correction(plan)
