"""Checks over the whole batch before the first file is processed.

Each check either lets the run go on or stops it with one batch-level event, so
the app has a single thing to ask about instead of a failure per file.
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from lib import ingest_media, tag_media
from lib.media_pipeline.consent import require_consent
from lib.media_pipeline.events import emit_event
from lib.media_pipeline.options import FIX_TIMESTAMP, RunOptions
from lib.timestamps.sources import normalize_timezone_input, read_file


def check_stale_exiftool_tmp(source_dir: str) -> None:
    """Stop on exiftool_tmp directories left by a crashed run: exiftool fails
    silently beside one. A terminal is offered to delete them."""
    tmp_dirs = list(Path(source_dir).rglob("exiftool_tmp"))
    if not tmp_dirs:
        return
    print(f"⚠️  Found {len(tmp_dirs)} stale exiftool_tmp director{'y' if len(tmp_dirs) == 1 else 'ies'} in source:", file=sys.stderr)
    for d in tmp_dirs:
        print(f"   {d}", file=sys.stderr)
    print(file=sys.stderr)

    require_consent(
        False, "Delete them? This will allow exiftool to run.",
        ["ERROR: Cannot proceed - exiftool will fail with these directories present.",
         "Delete the directories listed above, or re-run from a terminal to be prompted."],
        declined_line="ERROR: Cannot proceed - exiftool will fail with these directories present",
    )
    for d in tmp_dirs:
        shutil.rmtree(d)
    print("✅ Deleted exiftool_tmp directories", file=sys.stderr)


def check_protected_sources(files: list[Path], opts: RunOptions) -> None:
    """Report protected (locked) source files; an apply needs consent to import
    them unlocked."""
    protected = [fp.name for fp in files if ingest_media.is_protected(str(fp))]
    if not protected:
        return
    print(f"🔒 {len(protected)} source file(s) are protected (locked):", file=sys.stderr)
    for name in protected:
        print(f"   {name}", file=sys.stderr)
    print("Their imported copies will be unlocked; the source files stay locked.", file=sys.stderr)
    print(file=sys.stderr)
    emit_event("protected_sources", files=protected)
    if opts.apply:
        require_consent(opts.unlock_protected, "Import them unlocked?", [
            "ERROR: Cannot proceed without consent to import protected files unlocked.",
            "Re-run with --unlock-protected, or from a terminal to be prompted.",
        ])
    else:
        print("Previewing anyway; applying asks first (or pass --unlock-protected).", file=sys.stderr)
        print(file=sys.stderr)


def check_source_camera(files: list[Path], opts: RunOptions) -> None:
    """Hold every file to the profile's camera before anything is processed.

    A file shot on another camera means the profile was picked for the wrong
    body: a dry run reports it and previews anyway, an apply stops without
    --allow-camera-mismatch. A profile with no camera (for media that records
    none) is not checked.
    """
    expected = (opts.profile or {}).get("exif") or {}
    make, model = expected.get("make"), expected.get("model")

    if not make and not model:
        return

    mismatched = {fp.name: tag_media.camera_mismatch(str(fp), make, model) for fp in files}
    mismatched = {name: found for name, found in mismatched.items() if found}
    if not mismatched:
        return

    found_makes = sorted({f["Make"] for f in mismatched.values() if "Make" in f})
    found_models = sorted({f["Model"] for f in mismatched.values() if "Model" in f})
    expected_name = " ".join(v for v in (make, model) if v)
    print(f"📷 {len(mismatched)} file(s) were not shot on this profile's camera ({expected_name}):",
          file=sys.stderr)
    for name, found in mismatched.items():
        print(f"   {name}: {' '.join(found.values())}", file=sys.stderr)
    print("Their camera fields are left as the camera wrote them.", file=sys.stderr)
    print(file=sys.stderr)
    emit_event("camera_mismatch",
        files=list(mismatched),
        expected_make=make or None,
        expected_model=model or None,
        found_makes=found_makes,
        found_models=found_models,
    )
    if opts.apply:
        require_consent(opts.allow_camera_mismatch, "Import them anyway?", [
            "ERROR: Cannot proceed without consent to import files from another camera.",
            "Re-run with --allow-camera-mismatch, or pick the profile for this camera.",
        ])
    else:
        print("Previewing anyway; applying asks first (or pass --allow-camera-mismatch).", file=sys.stderr)
        print(file=sys.stderr)


# ---------------------------------------------------------------------------
# Timezones
# ---------------------------------------------------------------------------

MIXED_TIMEZONES = "mixed_timezones"
PROVIDED_MISMATCH = "provided_mismatch"


@dataclass(frozen=True)
class FileZone:
    """A file's zone (FileReading.zone) and the zone --timezone gives it, both as ±HHMM.

    tagged says the zone is a zoned tag's, which a correction to another zone
    would relabel; otherwise it is the camera's zone setting, which the UTC clock
    and the filename show and which correcting it is what the run is for.
    expected is None without --timezone. A zone name resolves per file, so each
    file is compared against the offset that zone had when that file was shot.
    """
    name: str
    embedded: str
    expected: Optional[str] = None
    tagged: bool = True


@dataclass(frozen=True)
class TimezoneConflict:
    """Why a batch's timezones stop the run.

    file_timezones groups files by zone, in file order: every file with a zone
    for mixed zones, the files with a zoned tag for a provided mismatch;
    mismatched holds, per tagged zone, the files --timezone disagrees with.
    """
    kind: str
    file_timezones: dict
    mismatched: dict


def read_file_zones(files: list[Path], timezone_spec: Optional[str]) -> list[FileZone]:
    """The zone and expected zone of every file with zone evidence; a file with
    none adds nothing to the comparison."""
    zones = []
    for fp in files:
        reading = read_file(str(fp))
        tz = reading.zone
        if not tz:
            continue
        expected = reading.declared_offset(timezone_spec)
        zones.append(FileZone(
            name=fp.name,
            embedded=normalize_timezone_input(tz).replace(":", ""),
            expected=expected.replace(":", "") if expected else None,
            tagged=reading.tagged_zone is not None,
        ))
    return zones


def preflight_timezones(zones: list[FileZone], allow_mixed: bool = False,
                        force: bool = False) -> Optional[TimezoneConflict]:
    """The batch's timezone conflict, or None when the run may go on.

    Files in different zones are mixed unless allow_mixed: a camera whose zone
    setting changed partway through a batch is as mixed as two zoned tags.
    Otherwise files whose zoned tag differs from the --timezone they were given
    are a provided mismatch unless force. A camera zone setting that differs is
    not: relabelling it is what the correction is for.
    """
    file_timezones: dict[str, list[str]] = {}
    for zone in zones:
        file_timezones.setdefault(zone.embedded, []).append(zone.name)

    if len(file_timezones) > 1 and not allow_mixed:
        return TimezoneConflict(MIXED_TIMEZONES, file_timezones, {})

    tagged_timezones: dict[str, list[str]] = {}
    expected_by_file = {}
    for zone in zones:
        if not zone.tagged:
            continue
        tagged_timezones.setdefault(zone.embedded, []).append(zone.name)
        if zone.expected:
            expected_by_file[zone.name] = zone.expected

    if expected_by_file and not force:
        mismatched = {
            tz: [name for name in names if expected_by_file.get(name, tz) != tz]
            for tz, names in tagged_timezones.items()
        }
        mismatched = {tz: names for tz, names in mismatched.items() if names}
        if mismatched:
            return TimezoneConflict(PROVIDED_MISMATCH, tagged_timezones, mismatched)
    return None


def check_timezones(files: list[Path], opts: RunOptions) -> None:
    """Stop before any file is processed when the batch's timezones conflict.

    A dry run previews a provided mismatch per file (each timestamp_result
    carries requires_force_timezone); only applying is refused.
    """
    if not opts.runs(FIX_TIMESTAMP) or opts.infer_from_filename:
        return
    zones = read_file_zones(files, opts.timezone_spec)
    compared = {zone.name for zone in zones}
    without_zone = [fp.name for fp in files if fp.name not in compared]
    if zones and without_zone:
        print(f"ℹ️  {len(without_zone)} file(s) hold no zone evidence and were not compared:",
              file=sys.stderr)
        for name in without_zone:
            print(f"   {name}", file=sys.stderr)
        print(file=sys.stderr)
    conflict = preflight_timezones(zones,
                                   allow_mixed=opts.allow_mixed_timezones,
                                   force=opts.force_timezone)
    if conflict is None:
        return

    if conflict.kind == MIXED_TIMEZONES:
        print("⚠️  Files have mixed timezones:", file=sys.stderr)
        for tz, names in sorted(conflict.file_timezones.items()):
            print(f"   {tz}: {', '.join(names)}", file=sys.stderr)
        print(file=sys.stderr)
        print("Consider processing timezone groups separately, or re-run with --force-timezone to proceed.", file=sys.stderr)
        emit_event("timezone_conflict",
            conflict_type=MIXED_TIMEZONES,
            file_timezones=dict(conflict.file_timezones),
        )
        sys.exit(1)

    print(f"⚠️  Timezone conflict: you provided {opts.timezone_spec} but files have different timezones:", file=sys.stderr)
    for tz, names in sorted(conflict.mismatched.items()):
        print(f"   {tz}: {', '.join(names)}", file=sys.stderr)
    print(file=sys.stderr)
    print("The embedded timezone is usually correct (set by the camera).", file=sys.stderr)
    if opts.apply:
        print("Re-run with --force-timezone to override.", file=sys.stderr)
    else:
        print("Previewing anyway; applying requires --force-timezone.", file=sys.stderr)
    emit_event("timezone_conflict",
        conflict_type=PROVIDED_MISMATCH,
        provided_tz=opts.timezone_spec,
        file_timezones=dict(conflict.file_timezones),
    )
    if opts.apply:
        sys.exit(1)


def check_filename_timestamps(files: list[Path], opts: RunOptions) -> None:
    """With --infer-from-filename, stop if any filename has no parseable timestamp."""
    if not opts.infer_from_filename:
        return
    unparseable = [fp.name for fp in files if read_file(str(fp)).filename_timestamp is None]
    if unparseable:
        print("⚠️  --infer-from-filename specified but these files have no parseable timestamp in their filename:", file=sys.stderr)
        for name in unparseable:
            print(f"   {name}", file=sys.stderr)
        emit_event("filename_parse_error", unparseable_files=unparseable)
        sys.exit(1)


def run_preflight(files: list[Path], opts: RunOptions) -> None:
    """Every batch-level check, in the order the user meets them."""
    check_protected_sources(files, opts)
    check_source_camera(files, opts)
    check_timezones(files, opts)
    check_filename_timestamps(files, opts)
