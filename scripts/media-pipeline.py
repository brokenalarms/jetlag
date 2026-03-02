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

import argparse
import json
import os
import re
import shutil
import signal
import sys
from pathlib import Path
from typing import Optional

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from lib.filesystem import find_media_files
from lib.timestamp_source import (
    build_filename, extract_metadata_timezone, normalize_timezone_input,
    parse_datetime_original, parse_filename_timestamp,
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


def signal_handler(sig, frame):
    """Handle Ctrl-C gracefully."""
    print("\n\nInterrupted by user", file=sys.stderr)
    sys.exit(130)


def load_config(profile_name: str) -> tuple[dict, dict]:
    """Load profile and top-level config from media-profiles.yaml.

    Returns:
        tuple of (profile_dict, full_config_dict)
    """
    profiles_file = SCRIPT_DIR / "media-profiles.yaml"
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
    timezone_offset: Optional[str],
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
        timezone_offset=timezone_offset,
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
):
    """Organize a file into date-based folders via direct module call.

    Returns:
        OrganizeResult dataclass.
    """
    return _organize_mod.process_file(
        str(file_path), target_dir, template,
        copy_mode=False, overwrite=False,
        apply=apply, verbose=verbose,
    )


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
):
    """Archive or delete source files via direct module call.

    Returns:
        ArchiveResult dataclass.
    """
    if action == "delete":
        return _archive_mod.delete_files(source_dir, files, apply)
    return _archive_mod.archive_source(source_dir, apply)


def process_file(
    file_path: Path,
    profile: Optional[dict],
    target_dir: str,
    working_dir: str,
    group: Optional[str],
    timezone_offset: Optional[str],
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
) -> dict:
    """Process a single file through the pipeline.

    Flow: INGEST (always) → [tag] → [fix-timestamp] → OUTPUT (always) → [gyroflow]

    Returns:
        dict with keys: changed, failed, error, source_files
    """
    result = {"changed": False, "failed": False, "error": None, "source_files": [str(file_path)]}
    file_changed = False

    emit_event("pipeline_file", file=file_path.name)

    # INGEST (always): copy source file to working dir
    print("📥 Ingesting...", file=sys.stderr)
    ingest_companions = companion_extensions if copy_companion_files else None
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
        emit_event("pipeline_result", file=file_path.name, result="failed")
        return result

    active_file = Path(dest) if action == "copied" else file_path
    if action == "copied":
        file_changed = True
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
                active_file, timezone_offset, apply,
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
        )

        if ts_result.timestamp_action == "error":
            print(f"   ❌ Timestamp fix failed for {file_path.name}", file=sys.stderr)
            result["failed"] = True
            result["error"] = "Timestamp fix failed"
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
                    else:
                        print(f"  [DRY RUN] Would rename: {active_file.name} → {new_name}", file=sys.stderr)
                    emit_event("rename_result",
                        file=active_file.name,
                        renamed_to=new_name,
                    )
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
    org_result = run_organize_by_date(active_file, target_dir, template, apply, verbose)
    emit_event("organize_result",
        file=active_file.name,
        action=org_result.action,
        dest=org_result.dest,
    )

    if org_result.action == "error":
        print(f"   ❌ Organization failed for {file_path.name}", file=sys.stderr)
        result["failed"] = True
        result["error"] = "Organization failed"
        emit_event("pipeline_result", file=file_path.name, result="failed")
        return result

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
    parser.add_argument("--timezone", help="Timezone in +HHMM format (e.g., +0800)")
    parser.add_argument("--group", help="Optional group folder name substituted for {{GROUP}} in the profile's folder_template, or inserted between year and date by default (e.g., 'Japan' → YYYY/Japan/YYYY-MM-DD)")
    parser.add_argument("--append-timezone-to-group", action="store_true", help="Append timezone offset to the group folder name (e.g., 'Japan' + '+0900' → 'Japan (+0900)'). Requires --group and --timezone.")
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
        "--allow-mixed-timezones", action="store_true",
        help="Allow processing files with different embedded timezones in a single batch. Without this flag, the pipeline stops when mixed timezones are detected."
    )
    parser.add_argument("--tags", help="Comma-separated Finder tags (overrides profile tags)")
    parser.add_argument("--make", help="EXIF camera make (overrides profile exif.make)")
    parser.add_argument("--model", help="EXIF camera model (overrides profile exif.model)")
    parser.add_argument(
        "--working-dir",
        default=os.path.expanduser("~/Library/Application Support/Jetlag/working"),
        help="Working directory for intermediate files (default: ~/Library/Application Support/Jetlag/working)"
    )
    return parser


def main():
    """Main entry point."""
    # Set up signal handler for Ctrl-C
    signal.signal(signal.SIGINT, signal_handler)

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

    # Validate timezone format if provided
    if args.timezone:
        if not re.match(r'^[+-]\d{4}$', args.timezone):
            print("ERROR: --timezone must be in +HHMM or -HHMM format (e.g., +0800, -0500)", file=sys.stderr)
            sys.exit(1)

    # Validate --append-timezone-to-group requirements
    if args.append_timezone_to_group:
        if not args.group:
            print("ERROR: --append-timezone-to-group requires --group", file=sys.stderr)
            sys.exit(1)
        if not args.timezone:
            print("ERROR: --append-timezone-to-group requires --timezone", file=sys.stderr)
            sys.exit(1)

    # Apply timezone suffix to group if requested
    group = args.group
    if group and args.append_timezone_to_group:
        group = f"{group} ({args.timezone})"

    # Validate --infer-from-filename and --time-offset requirements
    if args.infer_from_filename and not args.timezone:
        print("ERROR: --infer-from-filename requires --timezone", file=sys.stderr)
        sys.exit(1)
    if args.time_offset is not None and not args.timezone:
        print("ERROR: --time-offset requires --timezone", file=sys.stderr)
        sys.exit(1)

    # Resolve timezone upfront (direct module calls need the offset, not CLI args)
    timezone_offset = args.timezone
    if args.location and not timezone_offset:
        timezone_offset = _fix_ts_mod.get_timezone_for_country(args.location)
        if not timezone_offset:
            print(f"ERROR: Could not determine timezone for location '{args.location}'", file=sys.stderr)
            sys.exit(1)

    # Check for stale exiftool_tmp directories
    tmp_dirs = check_exiftool_tmp(source_dir)
    if tmp_dirs:
        print(f"⚠️  Found {len(tmp_dirs)} stale exiftool_tmp director{'y' if len(tmp_dirs) == 1 else 'ies'} in source:", file=sys.stderr)
        for d in tmp_dirs:
            print(f"   {d}", file=sys.stderr)
        print(file=sys.stderr)

        try:
            response = input("Delete them? This will allow exiftool to run. (y/n) ")
            if response.lower() == "y":
                for d in tmp_dirs:
                    shutil.rmtree(d)
                print("✅ Deleted exiftool_tmp directories", file=sys.stderr)
            else:
                print("ERROR: Cannot proceed - exiftool will fail with these directories present", file=sys.stderr)
                sys.exit(1)
        except EOFError:
            print("ERROR: Cannot proceed - exiftool will fail with these directories present", file=sys.stderr)
            sys.exit(1)

    # Set up working directory
    working_dir = args.working_dir
    if args.apply:
        os.makedirs(working_dir, exist_ok=True)

    # Display configuration
    print(f"→ Source:  {source_dir}", file=sys.stderr)
    print(f"→ Working: {working_dir}", file=sys.stderr)
    print(f"→ Target:  {target_dir}", file=sys.stderr)
    print(f"→ Mode:    {'APPLY (files will be processed)' if args.apply else 'DRY RUN (no changes)'}", file=sys.stderr)
    if timezone_offset:
        print(f"→ Timezone: {timezone_offset}", file=sys.stderr)
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
        for fp in files:
            tz = extract_metadata_timezone(str(fp))
            if tz:
                normalized = normalize_timezone_input(tz).replace(":", "")
                file_timezones.setdefault(normalized, []).append(fp.name)

        provided_tz_normalized = normalize_timezone_input(timezone_offset).replace(":", "") if timezone_offset else None

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
        if provided_tz_normalized and file_timezones and not args.force_timezone:
            mismatched = {tz: fnames for tz, fnames in file_timezones.items()
                          if tz != provided_tz_normalized}
            if mismatched:
                print(f"⚠️  Timezone conflict: you provided {timezone_offset} but files have different timezones:", file=sys.stderr)
                for tz, fnames in sorted(mismatched.items()):
                    print(f"   {tz}: {', '.join(fnames)}", file=sys.stderr)
                print(file=sys.stderr)
                print("The embedded timezone is usually correct (set by the camera).", file=sys.stderr)
                print("Re-run with --force-timezone to override.", file=sys.stderr)
                emit_event("timezone_conflict",
                    conflict_type="provided_mismatch",
                    provided_tz=timezone_offset,
                    file_timezones={tz: fnames for tz, fnames in file_timezones.items()},
                )
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
    tasks = set(args.tasks)

    companion_extensions = None
    if args.copy_companion_files and profile:
        companion_extensions = profile.get("companion_extensions")

    all_source_files = []

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
            timezone_offset,
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
        )

        if result["failed"]:
            stats["failed"] += 1
            stats["failed_files"].append(base)
        else:
            stats["succeeded"] += 1
            if result["changed"]:
                stats["changed"] += 1

        all_source_files.extend(result.get("source_files", []))

        print(file=sys.stderr)  # Empty line between files

    # Archive source (if in tasks)
    if "archive-source" in tasks:
        print("📦 Archive source...", file=sys.stderr)
        arc_result = run_archive_source(
            source_dir, args.source_action, all_source_files, args.apply,
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
                pass

    # Print summary
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
