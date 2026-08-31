#!/usr/bin/env python3
"""
media-pipeline.py
Orchestrates media processing: ingest from source, process, output to target.

Usage: media-pipeline.py --profile PROFILE [--group GROUP] [OPTIONS]
       media-pipeline.py --source DIR --target DIR [--group GROUP] [OPTIONS]

Pipeline: INGEST (always) → [tag] → [fix-timestamp] → OUTPUT (always) → [gyroflow] → [archive-source]

Source files are read-only inputs — ingest copies them to a working directory,
all processing happens there, then output moves files to the target.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import sys
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from lib.filesystem import find_media_files
from lib.metadata import metadata_service
from lib.profiles import resolve_profiles_file
from lib.timestamp_source import (
    build_filename, extract_metadata_timezone, is_zone_name, normalize_timezone_input,
    parse_datetime_original, parse_filename_timestamp, resolve_file_timezone_offset,
)

import importlib
_ingest_mod = importlib.import_module("ingest-media")
_tag_mod = importlib.import_module("tag-media")
_fix_ts_mod = importlib.import_module("fix-media-timestamp")
_organize_mod = importlib.import_module("organize-by-date")
_gyroflow_mod = importlib.import_module("generate-gyroflow")
_archive_mod = importlib.import_module("archive-source")

SCRIPT_DIR = Path(__file__).parent

_machine_output = not sys.stdout.isatty()


def emit_event(event_type: str, **fields) -> None:
    """Emit a JSONL event to stdout.

    Only emits when stdout is a pipe (macOS app), not a terminal (CLI).
    Flushes immediately so the app receives each line without buffering.

    None values are omitted. Lists, bools, and numbers stay as native JSON types.
    """
    if not _machine_output:
        return
    payload: dict = {"event": event_type}
    for key, value in fields.items():
        if value is None:
            continue
        payload[key] = value
    print(json.dumps(payload), flush=True)


SIGNAL_MESSAGES = {
    signal.SIGINT: "\n\nInterrupted by user",
    signal.SIGTERM: "\n\nCancelled",
}

EXIFTOOL_TMP_GLOB = "*_exiftool_tmp"

# Staging lives on the target's own volume, so ingest is a single same-volume
# copy and organize's move is a rename rather than a second full copy across
# volumes. The destination's free space is then the only limit on a batch.
WORKING_DIR_NAME = ".jetlag-working"

# The working directory is an implementation detail: nothing survives in it past
# the iteration of the file it was staged for. These hold what the run currently
# owns there, so a cancel can take it with it.
_staged_paths: list[Path] = []
_working_dir: Optional[str] = None


def register_staged_paths(paths: list[Path]) -> None:
    """Record the working-dir copies this file's iteration owns."""
    _staged_paths.clear()
    _staged_paths.extend(paths)


def discard_staged_paths() -> None:
    """Delete the staged copies of the file being processed, if they still exist.

    The source is never touched — a staged copy organize declined to place is a
    duplicate with no further use.
    """
    for path in _staged_paths:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError as e:
            print(f"   ⚠️  Could not discard staged copy {path.name}: {e}", file=sys.stderr)
    _staged_paths.clear()


def clean_working_dir_on_cancel() -> None:
    """Leave nothing behind: the in-flight copies, exiftool's scratch files, the dir.

    Only safe once the metadata service has been closed, because until then
    exiftool may still be writing the very files this removes.
    """
    discard_staged_paths()
    if _working_dir is None:
        return
    working = Path(_working_dir)
    if not working.is_dir():
        return
    for leftover in working.glob(EXIFTOOL_TMP_GLOB):
        try:
            leftover.unlink()
        except OSError:
            pass
    try:
        os.rmdir(working)
    except OSError:
        pass


def signal_handler(sig, frame):
    """Shut the metadata service down, clean the working dir, then exit.

    The metadata service owns a persistent jetlag-metadata process, which in
    turn owns an ``exiftool -stay_open`` process. Under the default SIGTERM
    disposition the interpreter dies without unwinding, so both are re-parented
    to launchd and keep running; closing the service here walks that chain down
    in order instead. Only once it has returned is the working directory quiet
    enough to clear.
    """
    print(SIGNAL_MESSAGES[sig], file=sys.stderr)
    metadata_service.close()
    clean_working_dir_on_cancel()
    sys.exit(128 + sig)


def load_config(profile_name: str) -> tuple[dict, dict]:
    """Load profile and top-level config from media-profiles.yaml.

    Returns:
        tuple of (profile_dict, full_config_dict)
    """
    profiles_file = resolve_profiles_file()
    if not profiles_file.exists():
        print(f"ERROR: Profile file not found: {profiles_file}", file=sys.stderr)
        sys.exit(1)

    with open(profiles_file) as f:
        data = yaml.safe_load(f)

    profiles = data.get("profiles", {})
    if profile_name not in profiles:
        available = ", ".join(profiles.keys())
        print(f"ERROR: Profile '{profile_name}' not found", file=sys.stderr)
        print(f"Available profiles: {available}", file=sys.stderr)
        sys.exit(1)

    return profiles[profile_name], data


def check_exiftool_tmp(source_dir: str) -> list[Path]:
    """Check for stale exiftool_tmp directories."""
    source = Path(source_dir)
    return list(source.rglob("exiftool_tmp"))


def run_tag_media(
    file_path: Path,
    tags: Optional[str],
    make: Optional[str],
    model: Optional[str],
    apply: bool
):
    """Tag a file via direct module call.

    Returns:
        TagResult on success, None on failure.
    """
    finder_tags = [t.strip() for t in tags.split(",")] if tags else []
    return _tag_mod.tag_media_file(
        str(file_path), finder_tags, make, model, dry_run=not apply
    )


def run_fix_timestamp(
    file_path: Path,
    timezone_spec: Optional[str],
    apply: bool,
    infer_from_filename: bool = False,
    time_offset: Optional[int] = None,
    force_timezone: bool = False,
):
    """Fix a file's timestamp via direct module call.

    Returns:
        TimestampFixResult dataclass.
    """
    return _fix_ts_mod.fix_media_timestamps(
        str(file_path),
        dry_run=not apply,
        timezone_spec=timezone_spec,
        infer_from_filename=infer_from_filename,
        time_offset_seconds=time_offset,
        force_timezone=force_timezone,
    )


def run_organize_by_date(
    file_path: Path,
    target_dir: str,
    template: str,
    apply: bool,
    verbose: bool,
    overwrite: bool = False,
    dest_name: Optional[str] = None,
):
    """Organize a file into date-based folders via direct module call.

    dest_name carries a pending rename's would-be basename into the destination
    path on a dry run; the file itself is read at file_path either way.

    Returns:
        OrganizeResult dataclass.
    """
    return _organize_mod.process_file(
        str(file_path), target_dir, template,
        copy_mode=False, overwrite=overwrite,
        apply=apply, verbose=verbose, dest_name=dest_name,
    )


# Organize is handed the working copy on an apply and the source file in a dry
# run, so it reports the staging hop: "moved"/"would_move". Neither is the user's
# outcome — the source directory is a read-only input that only archive-source
# ever touches, and what the destination gains is a new file. overwrote and
# would_overwrite describe the destination, not the source, so they carry over.
_STAGED_ORGANIZE_ACTION = {"moved": "copied", "would_move": "would_copy"}


def staged_organize_action(action: str) -> str:
    """Name organize's outcome relative to the user's source file.

    A dry run and the apply it previews go through this together, so both report
    the same outcome for the same file.
    """
    return _STAGED_ORGANIZE_ACTION.get(action, action)


# Organize logs the hop it performed on the file it was handed — the staged
# working copy on an apply. These are the pipeline's own lines, stating the
# same outcome for the file the user actually has. skipped and error are
# absent: organize's skip line and the pipeline's own "Organization failed"
# line already carry those.
_OUTCOME_LINE = {
    "copied": "✅ Copied: {source} → {dest}",
    "would_copy": "[DRY RUN] Would copy: {source} → {dest}",
    "overwrote": "♻️  Replaced at destination: {source} → {dest}",
    "would_overwrite": "[DRY RUN] Would replace at destination: {source} → {dest}",
}


def run_ingest_media(
    file_path: Path,
    working_dir: str,
    apply: bool,
    companion_extensions: list[str] | None = None,
) -> tuple[str, str, str, int, list[str]]:
    """Copy a source file into the flat working directory.

    Calls ingest-media.ingest_file() directly to avoid per-file subprocess overhead.

    Returns:
        tuple of (stderr_output, action, dest_path, return_code, companion_dests)
    """
    try:
        dest, action, companion_dests = _ingest_mod.ingest_file(
            str(file_path), working_dir, apply,
            companion_extensions=companion_extensions,
        )
        return "", action, dest, 0, companion_dests
    except Exception as e:
        return str(e), "", "", 1, []


def run_generate_gyroflow(
    file_path: Path,
    preset_json: str,
    apply: bool,
    binary: Optional[str] = None,
):
    """Generate a gyroflow project via direct module call.

    Returns:
        GyroflowResult dataclass.
    """
    return _gyroflow_mod.generate_gyroflow_project(
        file_path, apply, binary=binary, preset_json=preset_json,
    )


def run_archive_source(
    source_dir: str,
    action: str,
    files: list[str],
    apply: bool,
    destination: Optional[str] = None,
    archived_name: Optional[str] = None,
):
    """Archive or delete source files via direct module call.

    Returns:
        ArchiveResult dataclass.
    """
    if action == "delete":
        return _archive_mod.delete_files(source_dir, files, apply)
    return _archive_mod.archive_source(
        source_dir, apply, destination=destination, archived_name=archived_name,
    )


def process_file(
    file_path: Path,
    profile: Optional[dict],
    target_dir: str,
    working_dir: str,
    group: Optional[str],
    timezone_spec: Optional[str],
    apply: bool,
    verbose: bool,
    gyroflow_config: Optional[dict] = None,
    tasks: set | None = None,
    companion_extensions: list[str] | None = None,
    copy_companion_files: bool = False,
    update_filename_dates: bool = False,
    infer_from_filename: bool = False,
    time_offset: Optional[int] = None,
    force_timezone: bool = False,
    overwrite: bool = False,
) -> dict:
    """Process a single file through the pipeline.

    Flow: INGEST (always) → [tag] → [fix-timestamp] → OUTPUT (always) → [gyroflow]

    Returns:
        dict with keys: changed, failed, error, source_files, organize_conflict
    """
    result = {"changed": False, "failed": False, "error": None,
              "organize_conflict": None, "source_files": [str(file_path)]}
    file_changed = False
    # A dry run's --update-filename-dates rename that has not happened: the
    # would-be basename rides along for destination previews only.
    pending_rename_name = None

    emit_event("pipeline_file", file=file_path.name, source_path=str(file_path))

    # INGEST (always): copy source file to working dir
    print("📥 Ingesting...", file=sys.stderr)
    ingest_companions = companion_extensions if copy_companion_files else None
    # Registered before the copy starts, so a cancel mid-ingest still knows
    # which partial copy to take with it.
    register_staged_paths([Path(working_dir) / file_path.name] if apply else [])
    output, action, dest, rc, companion_dests = run_ingest_media(
        file_path, working_dir, apply, companion_extensions=ingest_companions,
    )
    if output:
        for line in output.split("\n"):
            if line.strip():
                print(f"  {line}", file=sys.stderr)

    if rc != 0:
        print(f"   ❌ Ingest failed for {file_path.name}", file=sys.stderr)
        result["failed"] = True
        result["error"] = "Ingest failed"
        _staged_paths.clear()
        emit_event("pipeline_result", file=file_path.name, result="failed")
        return result

    active_file = Path(dest) if action == "copied" else file_path
    if action == "copied":
        file_changed = True
        register_staged_paths([Path(dest)] + [Path(c) for c in companion_dests])
    emit_event("stage_complete", stage="ingest")

    if copy_companion_files and companion_dests:
        source_dir = file_path.parent
        stem = file_path.stem
        for ext in companion_extensions or []:
            companion_source = source_dir / (stem + ext)
            if companion_source.is_file():
                result["source_files"].append(str(companion_source))

    # Tag media (if in tasks and profile has tags/make/model)
    if tasks and "tag" in tasks and profile:
        tags = ",".join(profile.get("tags", []))
        exif = profile.get("exif", {})
        make = exif.get("make", "")
        model = exif.get("model", "")

        if tags or make or model:
            print("🏷️  Tagging...", file=sys.stderr)
            tag_result = run_tag_media(active_file, tags or None, make or None, model or None, apply)
            if tag_result is not None:
                emit_event("tag_result",
                    file=active_file.name,
                    action=tag_result.action,
                    tags_added=tag_result.tags_added,
                    exif_make=tag_result.exif_make,
                    exif_model=tag_result.exif_model,
                )
                if tag_result.action == "tagged":
                    file_changed = True
            emit_event("stage_complete", stage="tag")

    # Fix video timestamp (if in tasks)
    if tasks and "fix-timestamp" in tasks:
        print("🔧 Fixing timestamp...", file=sys.stderr)
        try:
            ts_result = run_fix_timestamp(
                active_file, timezone_spec, apply,
                infer_from_filename=infer_from_filename,
                time_offset=time_offset,
                force_timezone=force_timezone,
            )
        except Exception as e:
            error_msg = str(e)
            print(f"   ❌ {error_msg}", file=sys.stderr)
            emit_event("timestamp_result",
                file=active_file.name,
                action="error",
                error=error_msg,
            )
            result["failed"] = True
            result["error"] = error_msg
            _staged_paths.clear()
            emit_event("pipeline_result", file=file_path.name, result="failed")
            return result

        emit_event("timestamp_result",
            file=active_file.name,
            action=ts_result.timestamp_action,
            original_time=ts_result.original_time,
            corrected_time=ts_result.corrected_time,
            source=ts_result.timestamp_source,
            timezone=ts_result.timezone,
            correction_mode=ts_result.correction_mode,
            time_offset_seconds=ts_result.time_offset_seconds,
            time_offset_display=ts_result.time_offset_display,
            original_epoch=ts_result.original_epoch,
            corrected_epoch=ts_result.corrected_epoch,
            requires_force_timezone=bool(ts_result.requires_force_timezone),
            camera_zone_offset=ts_result.camera_zone_offset,
            stale_fields=ts_result.stale_fields,
        )

        if ts_result.timestamp_action == "error":
            print(f"   ❌ Timestamp fix failed for {file_path.name}", file=sys.stderr)
            result["failed"] = True
            result["error"] = "Timestamp fix failed"
            _staged_paths.clear()
            emit_event("pipeline_result", file=file_path.name, result="failed")
            return result

        if ts_result.timestamp_action in ("would_fix", "fixed"):
            file_changed = True
        emit_event("stage_complete", stage="fix-timestamp")

        # Inline rename when --update-filename-dates is set
        if update_filename_dates and ts_result.corrected_time:
            corrected_dt = parse_datetime_original(ts_result.corrected_time)
            if corrected_dt:
                new_name = build_filename(active_file.name, corrected_dt)
                if new_name and new_name != active_file.name:
                    new_path = active_file.parent / new_name
                    if apply:
                        os.rename(str(active_file), str(new_path))
                        # Rename companions in working dir and update companion_dests
                        updated_companion_dests = []
                        for ext in companion_extensions or []:
                            old_companion = active_file.parent / (active_file.stem + ext)
                            if old_companion.is_file():
                                new_companion = active_file.parent / (new_path.stem + ext)
                                os.rename(str(old_companion), str(new_companion))
                                updated_companion_dests.append(str(new_companion))
                        if updated_companion_dests:
                            companion_dests = updated_companion_dests
                        register_staged_paths(
                            [new_path] + [Path(c) for c in companion_dests])
                    else:
                        # The rename has not happened: active_file must keep
                        # pointing at the real file, and only the destination
                        # preview carries the would-be name.
                        print(f"  [DRY RUN] Would rename: {active_file.name} → {new_name}", file=sys.stderr)
                        pending_rename_name = new_name
                    emit_event("rename_result",
                        file=active_file.name,
                        renamed_to=new_name,
                    )
                    if apply:
                        active_file = new_path

    # OUTPUT (always): organize active_file to target_dir
    print("📁 Organizing by date...", file=sys.stderr)

    folder_template = profile.get("folder_template") if profile else None
    if folder_template:
        template = folder_template.replace("{{GROUP}}", group) if group else folder_template
    elif group:
        template = f"{{{{YYYY}}}}/{group}/{{{{YYYY}}}}-{{{{MM}}}}-{{{{DD}}}}"
    else:
        template = "{{YYYY}}/{{YYYY}}-{{MM}}-{{DD}}"
    org_result = run_organize_by_date(active_file, target_dir, template, apply, verbose,
                                      overwrite=overwrite, dest_name=pending_rename_name)
    staged_action = staged_organize_action(org_result.action)
    emit_event("organize_result",
        file=active_file.name,
        action=staged_action,
        dest=org_result.dest,
        reason=org_result.reason,
    )

    outcome_line = _OUTCOME_LINE.get(staged_action)
    if outcome_line:
        print(outcome_line.format(source=file_path, dest=org_result.dest), file=sys.stderr)

    # A file the destination already holds a different copy of is the one skip
    # --overwrite can resolve, so it is the only one the batch reports back.
    if (org_result.action == "skipped"
            and org_result.reason == _organize_mod.SKIP_EXISTS_DIFFERS):
        result["organize_conflict"] = active_file.name

    if org_result.action == "error":
        print(f"   ❌ Organization failed for {file_path.name}", file=sys.stderr)
        result["failed"] = True
        result["error"] = "Organization failed"
        _staged_paths.clear()
        emit_event("pipeline_result", file=file_path.name, result="failed")
        return result

    # A staged copy organize declined to place is a duplicate of a file already
    # at the destination, so it has no further use. Without this an idempotent
    # re-run stages the whole library into the working dir and leaves it there.
    if org_result.action == "skipped" and _staged_paths:
        print(f"   Discarded staged copy of {file_path.name} "
              f"(skipped: {org_result.reason})", file=sys.stderr)
        discard_staged_paths()

    if org_result.action in ("copied", "moved", "overwrote", "would_copy", "would_move", "would_overwrite"):
        file_changed = True

    dest = org_result.dest

    # Move companions to the same output directory as the main file
    if copy_companion_files and companion_dests and dest:
        output_dir = Path(dest).parent
        for companion_working_path in companion_dests:
            companion_file = Path(companion_working_path)
            companion_target = output_dir / companion_file.name
            if apply and companion_file.exists():
                os.makedirs(output_dir, exist_ok=True)
                shutil.move(str(companion_file), str(companion_target))
                print(f"  Companion: {companion_file.name} → {companion_target}", file=sys.stderr)
            elif not apply:
                print(f"  [DRY RUN] Would move companion: {companion_file.name} → {companion_target}", file=sys.stderr)
    _staged_paths.clear()
    emit_event("stage_complete", stage="output")

    # Generate gyroflow project (if in tasks, enabled, and applying)
    gyroflow_enabled = profile.get("gyroflow_enabled", False) if profile else False
    if tasks and "gyroflow" in tasks and gyroflow_enabled and gyroflow_config:
        print("🎥 Generating gyroflow project...", file=sys.stderr)

        preset = gyroflow_config.get("preset", {})
        preset_json = json.dumps(preset)
        binary = gyroflow_config.get("binary")

        gyroflow_file = Path(dest) if dest and apply else active_file
        gf_result = run_generate_gyroflow(gyroflow_file, preset_json, apply, binary=binary)
        emit_event("gyroflow_result",
            file=active_file.name,
            action=gf_result.action,
            gyroflow_path=gf_result.gyroflow_path,
            error=gf_result.error,
        )

        if gf_result.action == "generated":
            file_changed = True
        emit_event("stage_complete", stage="gyroflow")

    result["changed"] = file_changed
    if result["failed"]:
        emit_event("pipeline_result", file=file_path.name, result="failed")
    elif file_changed:
        emit_event("pipeline_result", file=file_path.name, result="changed" if apply else "would_change")
    else:
        emit_event("pipeline_result", file=file_path.name, result="unchanged")
    return result


def print_summary(stats: dict, apply: bool):
    """Print pipeline summary to stderr."""
    print(file=sys.stderr)
    print("===========================================", file=sys.stderr)
    print("📊 MEDIA PIPELINE SUMMARY", file=sys.stderr)
    print("-------------------------------------------", file=sys.stderr)
    print(f"Total files processed: {stats['processed']}", file=sys.stderr)
    print(f"Successfully completed: {stats['succeeded']}", file=sys.stderr)
    print(f"Files changed: {stats['changed']}", file=sys.stderr)
    print(f"Files unchanged: {stats['succeeded'] - stats['changed']}", file=sys.stderr)

    if stats["failed"] > 0:
        print(f"Failed: {stats['failed']}", file=sys.stderr)
        print(file=sys.stderr)
        print("Failed files:", file=sys.stderr)
        for f in stats["failed_files"]:
            print(f"  - {f}", file=sys.stderr)

    if apply:
        print("✅ Media pipeline complete - changes applied.", file=sys.stderr)
    else:
        print("✅ Media pipeline complete - DRY RUN.", file=sys.stderr)
        print("   Use --apply to execute timestamp fixes and file organization.", file=sys.stderr)


def build_parser():
    """Build the argument parser for media-pipeline."""
    parser = argparse.ArgumentParser(
        description="Orchestrates video timestamp fixing and organization into date-based folders."
    )
    parser.add_argument("--profile", help="Profile from media-profiles.yaml")
    parser.add_argument("--source", help="Directory containing video files (default: current directory)")
    parser.add_argument("--target", help="Target directory for organized files")
    parser.add_argument("--location", help="Location name/code for timezone lookup")
    parser.add_argument("--timezone", help="IANA zone name (e.g., Pacific/Auckland), resolved per file so a run spanning a DST changeover gets the right offset either side, or a fixed offset in +HHMM format (e.g., +0800)")
    parser.add_argument("--group", help="Optional group folder name substituted for {{GROUP}} in the profile's folder_template, or inserted between year and date by default (e.g., 'Japan' → YYYY/Japan/YYYY-MM-DD)")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default: dry run)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed processing info")
    parser.add_argument(
        "--tasks", nargs="+",
        choices=["tag", "fix-timestamp", "gyroflow", "archive-source"],
        default=["tag", "fix-timestamp", "gyroflow"],
        help="Optional pipeline steps to run (default: tag, fix-timestamp, gyroflow). Ingest and output are always on."
    )
    parser.add_argument(
        "--source-action",
        choices=["archive", "delete"],
        default="archive",
        help="Action for source after processing (default: archive). Requires archive-source in --tasks."
    )
    parser.add_argument(
        "--archive-destination",
        help="Directory to move the archived source folder into (default: where the source already is)."
    )
    parser.add_argument(
        "--archived-name",
        help="Name for the archived source folder (default: '<source> - copied <YYYY-MM-DD>')."
    )
    parser.add_argument(
        "--copy-companion-files", action="store_true",
        help="Also copy companion files (matching profile companion_extensions) to target."
    )
    parser.add_argument(
        "--infer-from-filename", action="store_true",
        help="Use filename timestamp as source of truth instead of EXIF metadata. Requires --timezone."
    )
    parser.add_argument(
        "--time-offset", type=int, default=None,
        help="Seconds to add/subtract from source timestamp (for clock correction). Requires --timezone."
    )
    parser.add_argument(
        "--update-filename-dates", action="store_true",
        help="Rename files to reflect corrected timestamps after fix-timestamp."
    )
    parser.add_argument(
        "--force-timezone", action="store_true",
        help="Override existing timezone in DateTimeOriginal with --timezone. Without this flag, the pipeline stops when a provided-vs-embedded conflict is detected."
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Replace files already at the organize destination. Without this flag, a destination already holding a different file is left alone and reported as a conflict."
    )
    parser.add_argument(
        "--allow-mixed-timezones", action="store_true",
        help="Allow processing files with different embedded timezones in a single batch. Without this flag, the pipeline stops when mixed timezones are detected."
    )
    parser.add_argument("--tags", help="Comma-separated Finder tags (overrides profile tags)")
    parser.add_argument("--make", help="EXIF camera make (overrides profile exif.make)")
    parser.add_argument("--model", help="EXIF camera model (overrides profile exif.model)")
    parser.add_argument(
        "--gyroflow-preset",
        help='JSON string overriding gyroflow stabilization preset from config (e.g. \'{"stabilization": {"max_zoom": 110.0}}\')'
    )
    parser.add_argument(
        "--working-dir",
        default=None,
        help=f"Working directory for intermediate files (default: <target>/{WORKING_DIR_NAME})"
    )
    return parser


def main():
    """Main entry point."""
    for sig in SIGNAL_MESSAGES:
        signal.signal(sig, signal_handler)

    parser = build_parser()
    args = parser.parse_args()

    # Load profile if specified
    profile = None
    full_config = {}
    if args.profile:
        profile, full_config = load_config(args.profile)

    # Apply CLI overrides to profile (workflow tab ad-hoc edits)
    if profile:
        if args.tags is not None:
            profile["tags"] = [t.strip() for t in args.tags.split(",") if t.strip()]
        if args.make is not None:
            profile.setdefault("exif", {})["make"] = args.make
        if args.model is not None:
            profile.setdefault("exif", {})["model"] = args.model

    # Determine source and target directories from profile or CLI args
    source_dir = args.source
    target_dir = args.target

    if profile:
        profile_source = profile.get("source_dir")
        ready_dir = profile.get("ready_dir")
        if not source_dir and profile_source and profile_source != "None":
            source_dir = profile_source
        if not target_dir and ready_dir and ready_dir != "None":
            target_dir = ready_dir

    if not source_dir:
        print("ERROR: --source is required (or use --profile with source_dir)", file=sys.stderr)
        sys.exit(1)

    if not target_dir:
        print("ERROR: --target is required (or use --profile with ready_dir)", file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(source_dir):
        print(f"ERROR: Source directory not found: {source_dir}", file=sys.stderr)
        sys.exit(1)

    # Validate timezone if provided
    if args.timezone:
        if is_zone_name(args.timezone):
            try:
                ZoneInfo(args.timezone)
            except (ZoneInfoNotFoundError, ValueError):
                print(f"ERROR: unknown timezone '{args.timezone}' — use an IANA zone name (e.g., Pacific/Auckland) or a +HHMM offset", file=sys.stderr)
                sys.exit(1)
        elif not re.match(r'^[+-]\d{4}$', args.timezone):
            print("ERROR: --timezone must be an IANA zone name (e.g., Pacific/Auckland) or in +HHMM format (e.g., +0800, -0500)", file=sys.stderr)
            sys.exit(1)

    group = args.group

    # Validate --infer-from-filename and --time-offset requirements
    if args.infer_from_filename and not args.timezone:
        print("ERROR: --infer-from-filename requires --timezone", file=sys.stderr)
        sys.exit(1)
    if args.time_offset is not None and not args.timezone:
        print("ERROR: --time-offset requires --timezone", file=sys.stderr)
        sys.exit(1)

    # Resolve timezone upfront (direct module calls need the offset, not CLI args)
    timezone_spec = args.timezone
    if args.location and not timezone_spec:
        timezone_spec = _fix_ts_mod.get_timezone_for_country(args.location)
        if not timezone_spec:
            print(f"ERROR: Could not determine timezone for location '{args.location}'", file=sys.stderr)
            sys.exit(1)

    # Check for stale exiftool_tmp directories
    tmp_dirs = check_exiftool_tmp(source_dir)
    if tmp_dirs:
        print(f"⚠️  Found {len(tmp_dirs)} stale exiftool_tmp director{'y' if len(tmp_dirs) == 1 else 'ies'} in source:", file=sys.stderr)
        for d in tmp_dirs:
            print(f"   {d}", file=sys.stderr)
        print(file=sys.stderr)

        # Prompt only on a real terminal. input() must never run otherwise: under
        # Xcode's Python it opens /dev/tty regardless of where stdin points, and a
        # non-interactive runner (tests, the app, a supervisor) reading the terminal
        # from a background process group is stopped by SIGTTIN — the whole run
        # freezes instead of failing.
        if sys.stdin.isatty() and sys.stderr.isatty():
            print("Delete them? This will allow exiftool to run. (y/n) ", end="", file=sys.stderr, flush=True)
            response = sys.stdin.readline().strip()
            if response.lower() == "y":
                for d in tmp_dirs:
                    shutil.rmtree(d)
                print("✅ Deleted exiftool_tmp directories", file=sys.stderr)
            else:
                print("ERROR: Cannot proceed - exiftool will fail with these directories present", file=sys.stderr)
                sys.exit(1)
        else:
            print("ERROR: Cannot proceed - exiftool will fail with these directories present.", file=sys.stderr)
            print("Delete the directories listed above, or re-run from a terminal to be prompted.", file=sys.stderr)
            sys.exit(1)

    # Set up working directory
    global _working_dir
    working_dir = args.working_dir or os.path.join(target_dir, WORKING_DIR_NAME)
    if args.apply:
        os.makedirs(working_dir, exist_ok=True)
        _working_dir = working_dir

    # Display configuration
    print(f"→ Source:  {source_dir}", file=sys.stderr)
    print(f"→ Target:  {target_dir}", file=sys.stderr)
    print(f"→ Mode:    {'APPLY (files will be processed)' if args.apply else 'DRY RUN (no changes)'}", file=sys.stderr)
    if timezone_spec:
        print(f"→ Timezone: {timezone_spec}", file=sys.stderr)
    else:
        print("→ Timezone: From video metadata (or will prompt if needed)", file=sys.stderr)
    if "archive-source" in args.tasks:
        print(f"→ Source action: {args.source_action}", file=sys.stderr)
    print(f"→ Copy companions: {'yes' if args.copy_companion_files else 'no'}", file=sys.stderr)
    print(file=sys.stderr)

    # Create target directory if needed
    if args.apply:
        os.makedirs(target_dir, exist_ok=True)

    # Find media files
    extensions = [".mp4", ".mov"]
    if profile:
        extensions = profile.get("file_extensions", extensions)

    files = find_media_files(source_dir, extensions)
    total_files = len(files)

    if total_files == 0:
        print(f"No video files found in {source_dir}", file=sys.stderr)
        sys.exit(0)

    print(f"📹 Found {total_files} video file(s) to process", file=sys.stderr)
    print(file=sys.stderr)

    # Pre-flight timezone check (before processing any files)
    if "fix-timestamp" in args.tasks and not args.infer_from_filename:
        file_timezones = {}
        # A zone name resolves per file, so each file is compared against the
        # offset that zone had when that file was shot.
        expected_by_file = {}
        for fp in files:
            tz = extract_metadata_timezone(str(fp))
            if tz:
                normalized = normalize_timezone_input(tz).replace(":", "")
                file_timezones.setdefault(normalized, []).append(fp.name)
                expected = resolve_file_timezone_offset(str(fp), timezone_spec)
                if expected:
                    expected_by_file[fp.name] = expected.replace(":", "")

        # Check 1: mixed timezones within the batch
        if len(file_timezones) > 1 and not args.allow_mixed_timezones:
            print("⚠️  Files have mixed timezones:", file=sys.stderr)
            for tz, fnames in sorted(file_timezones.items()):
                print(f"   {tz}: {', '.join(fnames)}", file=sys.stderr)
            print(file=sys.stderr)
            print("Consider processing timezone groups separately, or re-run with --force-timezone to proceed.", file=sys.stderr)
            emit_event("timezone_conflict",
                conflict_type="mixed_timezones",
                file_timezones={tz: fnames for tz, fnames in file_timezones.items()},
            )
            sys.exit(1)

        # Check 2: provided --timezone differs from files' embedded timezone
        if expected_by_file and not args.force_timezone:
            mismatched = {
                tz: [name for name in fnames if expected_by_file.get(name, tz) != tz]
                for tz, fnames in file_timezones.items()
            }
            mismatched = {tz: fnames for tz, fnames in mismatched.items() if fnames}
            if mismatched:
                print(f"⚠️  Timezone conflict: you provided {timezone_spec} but files have different timezones:", file=sys.stderr)
                for tz, fnames in sorted(mismatched.items()):
                    print(f"   {tz}: {', '.join(fnames)}", file=sys.stderr)
                print(file=sys.stderr)
                print("The embedded timezone is usually correct (set by the camera).", file=sys.stderr)
                if args.apply:
                    print("Re-run with --force-timezone to override.", file=sys.stderr)
                else:
                    print("Previewing anyway; applying requires --force-timezone.", file=sys.stderr)
                emit_event("timezone_conflict",
                    conflict_type="provided_mismatch",
                    provided_tz=timezone_spec,
                    file_timezones={tz: fnames for tz, fnames in file_timezones.items()},
                )
                # A dry run previews the relabel per file (each timestamp_result
                # carries requires_force_timezone); only applying is refused.
                if args.apply:
                    sys.exit(1)

    # Pre-flight filename parseability check (defense-in-depth for CLI users)
    if args.infer_from_filename:
        unparseable = [fp.name for fp in files if parse_filename_timestamp(str(fp))[0] is None]
        if unparseable:
            print("⚠️  --infer-from-filename specified but these files have no parseable timestamp in their filename:", file=sys.stderr)
            for name in unparseable:
                print(f"   {name}", file=sys.stderr)
            emit_event("filename_parse_error", unparseable_files=unparseable)
            sys.exit(1)

    # Process each file
    stats = {
        "processed": 0,
        "succeeded": 0,
        "changed": 0,
        "failed": 0,
        "failed_files": []
    }

    gyroflow_config = full_config.get("gyroflow")
    if args.gyroflow_preset:
        if gyroflow_config is None:
            gyroflow_config = {}
        gyroflow_config["preset"] = json.loads(args.gyroflow_preset)
    tasks = set(args.tasks)

    companion_extensions = None
    if args.copy_companion_files and profile:
        companion_extensions = profile.get("companion_extensions")

    all_source_files = []
    organize_conflicts = []

    for i, file_path in enumerate(files, 1):
        stats["processed"] += 1
        base = file_path.name

        print(f"[{i}/{total_files}] Processing: {base}", file=sys.stderr)

        result = process_file(
            file_path,
            profile,
            target_dir,
            working_dir,
            group,
            timezone_spec,
            args.apply,
            args.verbose,
            gyroflow_config=gyroflow_config,
            tasks=tasks,
            companion_extensions=companion_extensions,
            copy_companion_files=args.copy_companion_files,
            update_filename_dates=args.update_filename_dates,
            infer_from_filename=args.infer_from_filename,
            time_offset=args.time_offset,
            force_timezone=args.force_timezone,
            overwrite=args.overwrite,
        )

        if result["failed"]:
            stats["failed"] += 1
            stats["failed_files"].append(base)
        else:
            stats["succeeded"] += 1
            if result["changed"]:
                stats["changed"] += 1

        all_source_files.extend(result.get("source_files", []))
        if result.get("organize_conflict"):
            organize_conflicts.append(result["organize_conflict"])

        print(file=sys.stderr)  # Empty line between files

    # One batch-level report of what --overwrite would unblock, so the app has a
    # single thing to ask about instead of re-deriving it from the per-file rows.
    if organize_conflicts:
        print(f"⚠️  {len(organize_conflicts)} file(s) already at the destination with "
              "different contents. Re-run with --overwrite to replace them.", file=sys.stderr)
        emit_event("organize_conflict",
            count=len(organize_conflicts),
            files=organize_conflicts,
        )

    # Archive source (if in tasks) — a failed file's only copy may still be in
    # the source directory, so archiving it away after failures would strand it.
    if "archive-source" in tasks:
        if stats["failed"] > 0:
            print(f"📦 Skipping archive source: {stats['failed']} file(s) failed.", file=sys.stderr)
        else:
            print("📦 Archive source...", file=sys.stderr)
            arc_result = run_archive_source(
                source_dir, args.source_action, all_source_files, args.apply,
                destination=args.archive_destination,
                archived_name=args.archived_name,
            )
            if arc_result.failed:
                print("   ⚠️  Archive-source failed", file=sys.stderr)

    # Clean up working dir
    if args.apply:
        if stats["failed"] > 0:
            print(f"⚠️  Working dir preserved for inspection: {working_dir}", file=sys.stderr)
        else:
            try:
                os.rmdir(working_dir)
            except OSError:
                leftovers = len(os.listdir(working_dir)) if os.path.isdir(working_dir) else 0
                if leftovers:
                    print(f"⚠️  {leftovers} file(s) left in the working dir after a run "
                          "with no failures", file=sys.stderr)

    # The run's outcome as data, for the app's completion popup. print_summary
    # writes the same counts to stderr for the log; neither side reads the other.
    emit_event("pipeline_summary",
        processed=stats["processed"],
        succeeded=stats["succeeded"],
        changed=stats["changed"],
        failed=stats["failed"],
        failed_files=stats["failed_files"],
        mode="applied" if args.apply else "dry_run",
    )
    print_summary(stats, args.apply)

    # Exit with error if any files failed
    sys.exit(1 if stats["failed"] > 0 else 0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        emit_event("pipeline_error", message=str(e))
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
