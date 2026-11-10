"""Applying a correction: at most one exiftool write, and the result."""

from __future__ import annotations

import sys

from lib.exiftool import MetadataWriteRefused, exiftool
from lib.fix_media_timestamp.plan import (
    NO_TIMESTAMP, REFUSED_WITHOUT_FORCE, ZONE_NEEDED, CorrectionPlan, TimestampFixResult,
    machine_original_time,
)


def apply_correction(plan: CorrectionPlan) -> TimestampFixResult:
    """Carry the plan out — at most one exiftool write — and report the result."""
    data = plan.current.data
    if plan.problem == REFUSED_WITHOUT_FORCE:
        return TimestampFixResult(
            file=plan.filename,
            timestamp_action="error",
            original_time=machine_original_time(data),
            timezone=plan.current.detected_tz,
            requires_force_timezone=True,
        )
    if plan.problem == ZONE_NEEDED:
        return TimestampFixResult(
            file=plan.filename,
            timestamp_action="error",
            original_time=data["exif"].get("CreateDate", ""),
            timezone=plan.current.detected_tz,
        )
    if plan.problem == NO_TIMESTAMP:
        return TimestampFixResult(file=plan.filename, timestamp_action="error",
                                  timezone=plan.current.detected_tz)

    if not plan.opts.apply:
        if plan.has_changes:
            return plan.result("would_add" if plan.only_adds_fields else "would_fix")
        return plan.result("no_change")
    if not plan.writes:
        return plan.result("no_change")

    write_args = plan.provenance_args + plan.correction_args + plan.extra_args + plan.file_time_args
    succeeded = True
    write_error = None
    if write_args:
        try:
            written = exiftool.write_tags(plan.current.file_path, write_args)
        except MetadataWriteRefused as refusal:
            written, write_error = False, str(refusal)
            print(f"   ❌ exiftool could not write this file: {write_error}", file=sys.stderr)
        if not written:
            if plan.provenance_args:
                print("   ⚠️  Failed to record original timestamps for recovery", file=sys.stderr)
            if plan.correction_args:
                print(f"   ❌ Failed to write clock fields: {', '.join(plan.changes['clock_targets'])}", file=sys.stderr)
            if plan.extra_args:
                print(f"   ❌ Failed to write {', '.join(plan.opts.extra_write_fields)}", file=sys.stderr)
            if plan.file_time_args:
                print("   ❌ Failed to apply file timestamps", file=sys.stderr)
            succeeded = not (plan.correction_args or plan.extra_args or plan.file_time_args)

    if not succeeded:
        return plan.result("error", error=write_error)
    if not plan.has_changes:
        return plan.result("no_change")
    return plan.result("added" if plan.only_adds_fields else "fixed")
