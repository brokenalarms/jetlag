"""Describing a correction: the change as the user reads it on stderr."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from lib.fix_media_timestamp.clock_fields import CLOCK_FIELDS
from lib.fix_media_timestamp.plan import BIRTH_TIME_IN_FUTURE, NO_TIMESTAMP, REFUSED_WITHOUT_FORCE, ZONE_NEEDED, CorrectionPlan
from lib.fix_media_timestamp.read import FIELD_LABELS
from lib.timestamps.sources import MOVIE_HEADER_CREATE_DATE_TAG, TimestampSource, trailing_zone


def format_exif_timestamp_display(ts: str) -> str:
    """Format EXIF timestamp with dashes for date, colons for time"""
    # Convert YYYY:MM:DD HH:MM:SS to YYYY-MM-DD HH:MM:SS
    return ts.replace(':', '-', 2) if ts else ts

def format_original_timestamps(current_data: dict) -> str:
    """Format original timestamp display from raw data"""
    parts = []

    # Show the timestamp source that was actually used
    source = current_data.get("timestamp_source", TimestampSource.NONE)

    if source.field in FIELD_LABELS:
        value = current_data["exif"].get(source.field, "")
        if value:
            utc_suffix = " UTC" if source.is_utc else ""
            parts.append(f"{format_exif_timestamp_display(value)} ({FIELD_LABELS[source.field]}{utc_suffix})")
    elif source.field == MOVIE_HEADER_CREATE_DATE_TAG:
        media_create = current_data["exif"].get(MOVIE_HEADER_CREATE_DATE_TAG, "")
        birth_ts = current_data["file_system"].get("birth", "")
        if media_create:
            parts.append(f"{format_exif_timestamp_display(media_create)} UTC (QuickTime:CreateDate)")
        if birth_ts:
            parts.append(f"{format_exif_timestamp_display(birth_ts)} local (file)")
    elif source in (TimestampSource.FILENAME, TimestampSource.FILENAME_INFERRED):
        # Show the parsed filename timestamp
        filename_ts = current_data.get("filename_timestamp")
        if filename_ts:
            parts.append(f"{format_exif_timestamp_display(filename_ts)} (from filename)")
        else:
            parts.append("(from filename)")
    elif source is TimestampSource.FILE_BIRTH:
        birth_ts = current_data["file_system"].get("birth", "")
        if birth_ts:
            parts.append(f"{format_exif_timestamp_display(birth_ts)} (file birth)")
    elif source is TimestampSource.FILE_MTIME:
        mod_ts = current_data["file_system"].get("modify", "")
        if mod_ts:
            parts.append(f"{format_exif_timestamp_display(mod_ts)} (file modified)")

    return ", ".join(parts) if parts else "(no timestamps available)"

def format_timestamp_display(dt: datetime) -> str:
    """Format timestamp with dashes for date, colons for time"""
    return dt.strftime('%Y-%m-%d %H:%M:%S%z')

def format_corrected_timestamp(datetime_original: datetime, timestamp_source: TimestampSource, timezone_source: str) -> str:
    """Format corrected timestamp display"""
    corrected_str = format_timestamp_display(datetime_original)
    tz_value = datetime_original.strftime('%z')
    # Format timezone with colon
    tz_formatted = f"{tz_value[:3]}:{tz_value[3:]}" if len(tz_value) == 5 else tz_value

    source_display = FIELD_LABELS.get(timestamp_source.field or "", timestamp_source.display)

    # Use the actual timezone source
    tz_source_display = timezone_source if timezone_source else f"{source_display} metadata ({tz_formatted})"
    if not timezone_source.startswith("--timezone"):
        tz_source_display = f"{timezone_source} ({tz_formatted})"

    return f"{corrected_str} (from {source_display} with timezone, tz: {tz_source_display})"

def format_time_delta(seconds: float) -> str:
    """Format time delta showing hours, rounded to nearest hour if within 2 minutes"""
    sign = "+" if seconds > 0 else "-"
    total_seconds = abs(seconds)
    total_minutes = total_seconds / 60
    hours = total_minutes / 60

    # Round to nearest hour if within 2 minutes of a whole hour
    nearest_hour = round(hours)
    if nearest_hour > 0 and abs(hours - nearest_hour) * 60 < 2:  # within 2 minutes
        return f"{sign}{nearest_hour} hour{'s' if nearest_hour != 1 else ''}"

    # Otherwise show exact hours and minutes
    hours = int(total_minutes // 60)
    minutes = int(total_minutes % 60)

    if minutes == 0:
        return f"{sign}{hours} hour{'s' if hours != 1 else ''}"
    elif hours == 0:
        return f"{sign}{minutes} minute{'s' if minutes != 1 else ''}"
    else:
        return f"{sign}{hours}h {minutes}m"

def format_change_description(changes: dict, timestamp_data: Optional[dict] = None, current_data: Optional[dict] = None, preserve_wallclock: bool = False, datetime_original: Optional[datetime] = None) -> str:
    """Format change description from changes data"""
    parts = []
    stale = changes.get("stale_clock_fields", [])
    targets = changes.get("clock_targets", {})
    exif = current_data.get("exif", {}) if current_data else {}

    if "DateTimeOriginal" in stale:
        current_dto = exif.get("DateTimeOriginal", "")
        if current_dto:
            parts.append(f"DateTimeOriginal ({format_exif_timestamp_display(current_dto)}"
                         f" → {format_exif_timestamp_display(targets['DateTimeOriginal'])})")
        else:
            parts.append("DateTimeOriginal (missing)")

    if "OffsetTimeOriginal" in stale:
        current_offset = exif.get("OffsetTimeOriginal", "")
        parts.append(f"OffsetTimeOriginal ({current_offset or 'missing'}"
                     f" → {targets['OffsetTimeOriginal']})")

    if "Keys:CreationDate" in stale:
        # Show helpful context for Keys:CreationDate change
        if current_data and datetime_original:
            creation_date = current_data.get("exif", {}).get("CreationDate", "")
            time_display = datetime_original.strftime('%H:%M')

            if preserve_wallclock:
                # Preserving wall-clock time, updating timezone
                current_tz_offset = time.strftime('%z')
                current_tz_formatted = f"{current_tz_offset[:3]}:{current_tz_offset[3:]}"

                # Extract current timezone from existing CreationDate if present
                if creation_date:
                    old_tz = trailing_zone(creation_date)
                    if old_tz and old_tz != "Z":
                        parts.append(f"Keys:CreationDate ({old_tz} → {current_tz_formatted}, preserving {time_display} shooting time)")
                    else:
                        parts.append(f"Keys:CreationDate (adding {current_tz_formatted}, preserving {time_display} shooting time)")
                else:
                    parts.append(f"Keys:CreationDate (missing, setting to {time_display} in {current_tz_formatted})")
            else:
                # Updating to match DateTimeOriginal
                orig_tz = datetime_original.strftime('%z')
                orig_tz_formatted = f"{orig_tz[:3]}:{orig_tz[3:]}"
                if creation_date:
                    parts.append(f"Keys:CreationDate (updating to {orig_tz_formatted})")
                else:
                    parts.append(f"Keys:CreationDate (missing, setting to {time_display} with {orig_tz_formatted})")
        else:
            parts.append("Keys:CreationDate")

    if changes.get("file_timestamps"):
        if timestamp_data and timestamp_data.get("expected_time"):
            birth_delta = timestamp_data.get("birth_delta_seconds")
            current_birth_str = timestamp_data.get("current_birth")

            if birth_delta is not None and abs(birth_delta) > 1:
                expected_dt = datetime.strptime(timestamp_data["expected_time"], '%Y:%m:%d %H:%M:%S')

                # Check if dates differ (not just times)
                current_birth_dt: Optional[datetime] = None
                if current_birth_str:
                    current_birth_dt = datetime.strptime(current_birth_str, '%Y:%m:%d %H:%M:%S')
                    dates_differ = current_birth_dt.date() != expected_dt.date()
                else:
                    dates_differ = False

                if dates_differ and current_birth_dt is not None:
                    # Show full date change: "2025-12-06 → 2025-10-05 10:00"
                    current_display = current_birth_dt.strftime('%Y-%m-%d %H:%M')
                    expected_display = expected_dt.strftime('%Y-%m-%d %H:%M')
                    parts.append(f"Birth time ({current_display} → {expected_display})")
                else:
                    # Same date, just show time change
                    delta_str = format_time_delta(birth_delta)
                    time_display = expected_dt.strftime('%H:%M')
                    if preserve_wallclock:
                        parts.append(f"Birth time ({delta_str} to {time_display}, shooting time)")
                    else:
                        system_tz_offset = time.strftime('%z')
                        system_tz_formatted = f"{system_tz_offset[:3]}:{system_tz_offset[3:]}"
                        parts.append(f"Birth time ({delta_str} to {time_display}, display time in {system_tz_formatted})")
            else:
                parts.append("Birth time")
        else:
            parts.append("Birth time")

    for field in CLOCK_FIELDS:
        if not field.quicktime or field.write_tag not in stale:
            continue
        current = exif.get(field.read_key, "")
        target_display = f"{format_exif_timestamp_display(targets[field.write_tag])} UTC"
        if current:
            parts.append(f"{field.write_tag} ({format_exif_timestamp_display(current)} → {target_display})")
        else:
            parts.append(f"{field.write_tag} (missing → {target_display})")

    return ", ".join(parts) if parts else "No change"


def describe_correction(plan: CorrectionPlan) -> str:
    """The correction as the user reads it on stderr."""
    data = plan.current.data
    lines = [f"\033[36m🔍 {plan.filename}\033[0m"]

    if plan.requires_force_timezone:
        lines.append(f"⚠️  File already carries timezone {plan.current.detected_tz}; "
                     f"declared {data.get('timezone_offset')} relabels it")
        if plan.problem == REFUSED_WITHOUT_FORCE:
            lines.append("❌ Refusing to apply without --force-timezone.")
            return "\n".join(lines)
        lines.append("   Applying requires --force-timezone.")

    if plan.problem == ZONE_NEEDED:
        lines += [
            "❌ File has CreateDate but no DateTimeOriginal",
            f"   CreateDate: {data['exif'].get('CreateDate', '')}",
            "   Use --timezone to specify timezone (e.g., --timezone +09:00)",
        ]
        return "\n".join(lines)
    if plan.problem == NO_TIMESTAMP:
        lines.append("❌ No valid DateTimeOriginal found")
        return "\n".join(lines)

    corrected = plan.corrected
    assert corrected is not None
    lines.append(f"📅 Original : {format_original_timestamps(data)}")
    lines.append(f"⏱️ Corrected: {format_corrected_timestamp(corrected, data['timestamp_source'], data.get('timezone_source', ''))}")
    lines.append(f"🌐 UTC      : {corrected.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    if plan.problem == BIRTH_TIME_IN_FUTURE:
        assert plan.birth_time is not None
        expected = format_exif_timestamp_display(plan.birth_time["expected_time"])
        lines.append(f"❌ Birth time would be {expected}, later than now: refusing to write it.")
        lines.append("   Check --time-offset or --preserve-wallclock.")
        return "\n".join(lines)

    change_desc = format_change_description(plan.changes, plan.birth_time, data,
                                            plan.opts.preserve_wallclock, corrected)
    dry_run = " (DRY RUN)" if not plan.opts.apply and plan.has_changes else ""
    lines.append(f"📊 Change   : {change_desc}{dry_run}")

    if plan.writes and plan.write_datetime_original and data["exif"].get("DateTimeOriginal"):
        if plan.opts.infer_from_filename:
            lines.append("   ⚠️  Overwriting existing DateTimeOriginal (--infer-from-filename flag)")
        elif plan.opts.force_timezone:
            lines.append("   ⚠️  Overwriting existing DateTimeOriginal timezone (--force-timezone flag)")
    return "\n".join(lines)
