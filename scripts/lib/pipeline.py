"""
The media pipeline: ingest from source, process, output to target.

Pipeline: INGEST (always) → [tag] → [fix-timestamp] → OUTPUT (always) → [gyroflow] → [archive-source]

Source files are read-only inputs — ingest copies them to a working directory,
all processing happens there, then output moves files to the target. Each step
is a call into its lib module; media-pipeline.py is the command line.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from lib import archive, fix_timestamp, gyroflow, ingest, organize, profiles, tagging
from lib.cli import UnknownLocation, UnknownTimezone, interrupt_handler, resolve_timezone
from lib.exiftool import MetadataWriteRefused
from lib.filesystem import find_media_files
from lib.timestamp_source import (
    build_filename, carry_exif_cache, extract_metadata_timezone, normalize_timezone_input, parse_datetime_original, parse_filename_timestamp,
    read_exif_data, resolve_file_timezone_offset,
)

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


EXIFTOOL_TMP_GLOB = "*_exiftool_tmp"

# Staging lives on the target's own volume, so ingest is a single same-volume
# copy and organize's move is a rename rather than a second full copy across
# volumes. The destination's free space is then the only limit on a batch.
WORKING_DIR_NAME = ".jetlag-working"

class WorkingDir:
    """The staging directory and the copies in it the run currently owns.

    The working directory is an implementation detail: nothing survives in it past
    the iteration of the file it was staged for. The cancel handler closes over
    this object, so a cancel can take what the run owns with it.
    """

    def __init__(self, path: str = "", created: bool = False):
        self.path = path
        self.created = created
        self.staged: list[Path] = []

    def create(self) -> None:
        """Create the directory an apply stages into; a cancel now clears it."""
        os.makedirs(self.path, exist_ok=True)
        self.created = True

    def stage(self, paths: list[Path]) -> None:
        """Record the working-dir copies this file's iteration owns."""
        self.staged = list(paths)

    def release(self) -> None:
        """Stop owning the staged copies without touching them: they have been
        moved out, or are kept for inspection after a failure."""
        self.staged = []

    def discard(self) -> None:
        """Delete the staged copies of the file being processed, if they still exist.

        The source is never touched — a staged copy organize declined to place is a
        duplicate with no further use.
        """
        for path in self.staged:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError as e:
                print(f"   ⚠️  Could not discard staged copy {path.name}: {e}", file=sys.stderr)
        self.staged = []

    def clean_on_cancel(self) -> None:
        """Leave nothing behind: the in-flight copies, exiftool's scratch files, the dir.

        Only safe once the metadata service has been closed, because until then
        exiftool may still be writing the very files this removes.
        """
        self.discard()
        if not self.created:
            return
        working = Path(self.path)
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


def cancel_handler(working_dir: WorkingDir):
    """The SIGINT/SIGTERM handler for a run staging into working_dir.

    Cancel shuts exiftool down first; only then is the working directory quiet
    enough to clear.
    """
    return interrupt_handler(working_dir.clean_on_cancel)


def require_consent(granted: bool, prompt: str, refusal_lines: list[str],
                    declined_line: str = "Cancelled.", stdin=None, stderr=None) -> None:
    """Go on only with the user's consent; otherwise exit 1.

    granted is consent already given by a flag. Without it, a real terminal is
    asked the y/n prompt (declined_line answers anything but y), and anything
    else is refused with refusal_lines, which say how to give consent.

    The prompt only ever runs on a real terminal. Reading stdin otherwise must
    never happen: under Xcode's Python input() opens /dev/tty regardless of where
    stdin points, and a non-interactive runner (tests, the app, a supervisor)
    reading the terminal from a background process group is stopped by SIGTTIN —
    the whole run freezes instead of failing.
    """
    if granted:
        return
    stdin = stdin or sys.stdin
    stderr = stderr or sys.stderr
    if stdin.isatty() and stderr.isatty():
        print(f"{prompt} (y/n) ", end="", file=stderr, flush=True)
        if stdin.readline().strip().lower() == "y":
            return
        print(declined_line, file=stderr)
        sys.exit(1)
    for line in refusal_lines:
        print(line, file=stderr)
    sys.exit(1)


def load_config(profile_name: str) -> tuple[dict, dict]:
    """The named profile and the whole profiles file, or exit naming what is wrong."""
    try:
        config = profiles.load_config()
        return profiles.load_profile(profile_name, config), config
    except profiles.ProfilesFileMissing as missing:
        print(f"ERROR: Profile file not found: {missing.path}", file=sys.stderr)
        sys.exit(1)
    except profiles.ProfileNotFound as not_found:
        print(f"ERROR: Profile '{profile_name}' not found", file=sys.stderr)
        print(f"Available profiles: {', '.join(not_found.available)}", file=sys.stderr)
        sys.exit(1)


def check_exiftool_tmp(source_dir: str) -> list[Path]:
    """Check for stale exiftool_tmp directories."""
    source = Path(source_dir)
    return list(source.rglob("exiftool_tmp"))


def check_source_camera(files: list[Path], profile: Optional[dict], apply: bool,
                        allow_mismatch: bool) -> None:
    """Hold every file to the profile's camera before anything is processed.

    A file shot on another camera means the profile was picked for the wrong
    body: a dry run reports it and previews anyway, an apply stops without
    --allow-camera-mismatch. A profile with no camera (for media that records
    none) is not checked.
    """
    expected = (profile or {}).get("exif") or {}
    make, model = expected.get("make"), expected.get("model")

    if not make and not model:
        return

    mismatched = {fp.name: tagging.camera_mismatch(str(fp), make, model) for fp in files}
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
    if apply:
        require_consent(allow_mismatch, "Import them anyway?", [
            "ERROR: Cannot proceed without consent to import files from another camera.",
            "Re-run with --allow-camera-mismatch, or pick the profile for this camera.",
        ])
    else:
        print("Previewing anyway; applying asks first (or pass --allow-camera-mismatch).", file=sys.stderr)
        print(file=sys.stderr)


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


def process_file(
    file_path: Path,
    profile: Optional[dict],
    target_dir: str,
    working_dir: WorkingDir,
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
    result: Dict[str, Any] = {"changed": False, "failed": False, "error": None,
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
    working_dir.stage([Path(working_dir.path) / file_path.name] if apply else [])
    try:
        dest, action, companion_dests = ingest.ingest_file(
            str(file_path), working_dir.path, apply, companion_extensions=ingest_companions,
        )
        ingest_error = None
    except Exception as e:
        dest, action, companion_dests, ingest_error = "", "", [], str(e)
    if ingest_error:
        for line in ingest_error.split("\n"):
            if line.strip():
                print(f"  {line}", file=sys.stderr)

    if ingest_error is not None:
        print(f"   ❌ Ingest failed for {file_path.name}", file=sys.stderr)
        result["failed"] = True
        result["error"] = "Ingest failed"
        working_dir.release()
        emit_event("pipeline_result", file=file_path.name, result="failed")
        return result

    active_file = Path(dest) if action == "copied" else file_path
    if action == "copied":
        file_changed = True
        working_dir.stage([Path(dest)] + [Path(c) for c in companion_dests])
        carry_exif_cache(str(file_path), dest)
    emit_event("stage_complete", stage="ingest")

    # The file's one metadata read (or the pre-flight's, carried to the copy above).
    # Taken before any step writes, so organize never reads the file again; a
    # timestamp correction replaces it with the corrected value below.
    organize_datetime_original = read_exif_data(str(active_file)).get("DateTimeOriginal", "")
    # Every step's field writes go out in fix-timestamp's exiftool call, so the file
    # is rewritten once.
    fix_writes_fields = apply and bool(tasks) and "fix-timestamp" in tasks

    if copy_companion_files and companion_dests:
        source_dir = file_path.parent
        stem = file_path.stem
        for ext in companion_extensions or []:
            companion_source = source_dir / (stem + ext)
            if companion_source.is_file():
                result["source_files"].append(str(companion_source))

    camera_fields: dict = {}
    # Tag media (if in tasks and profile has tags/make/model)
    if tasks and "tag" in tasks and profile:
        finder_tags = tagging.parse_tag_list(",".join(profile.get("tags", [])))
        exif = profile.get("exif", {})
        make = exif.get("make", "")
        model = exif.get("model", "")

        if finder_tags or make or model:
            print("🏷️  Tagging...", file=sys.stderr)
            try:
                tag_result = tagging.tag_media_file(
                    str(active_file), finder_tags, make or None, model or None,
                    apply=apply, write_exif=not fix_writes_fields)
            except MetadataWriteRefused as refusal:
                print(f"   ❌ exiftool could not write {active_file.name}: {refusal}", file=sys.stderr)
                result["failed"] = True
                result["error"] = str(refusal)
                working_dir.release()
                emit_event("pipeline_result", file=file_path.name, result="failed")
                return result
            if fix_writes_fields:
                camera_fields = tagging.camera_exif_fields(str(active_file), make or None, model or None)
            if tag_result is not None:
                emit_event("tag_result",
                    file=active_file.name,
                    action=tag_result.action,
                    tags_added=tag_result.tags_added,
                    exif_make=tag_result.exif_make,
                    exif_model=tag_result.exif_model,
                    file_make=tag_result.file_make,
                    file_model=tag_result.file_model,
                )
                if tag_result.action == "tagged":
                    file_changed = True
            emit_event("stage_complete", stage="tag")

    # Fix video timestamp (if in tasks)
    if tasks and "fix-timestamp" in tasks:
        print("🔧 Fixing timestamp...", file=sys.stderr)
        try:
            ts_result = fix_timestamp.fix_media_timestamps(
                str(active_file),
                apply=apply,
                timezone_spec=timezone_spec,
                infer_from_filename=infer_from_filename,
                time_offset_seconds=time_offset,
                force_timezone=force_timezone,
                extra_write_fields=camera_fields,
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
            working_dir.release()
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
            stale_file_times=ts_result.stale_file_times,
            error=ts_result.error,
        )

        if ts_result.timestamp_action == "error":
            print(f"   ❌ Timestamp fix failed for {file_path.name}", file=sys.stderr)
            result["failed"] = True
            result["error"] = ts_result.error or "Timestamp fix failed"
            working_dir.release()
            emit_event("pipeline_result", file=file_path.name, result="failed")
            return result

        if ts_result.timestamp_action in ("would_fix", "fixed", "would_add", "added"):
            file_changed = True
        if ts_result.corrected_time:
            organize_datetime_original = ts_result.corrected_time
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
                        working_dir.stage(
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
    org_result = organize.process_file(
        str(active_file), target_dir, folder_template or None, group=group,
        copy_mode=False, overwrite=overwrite, apply=apply, verbose=verbose,
        dest_name=pending_rename_name, datetime_original=organize_datetime_original,
    )
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
            and org_result.reason == organize.SKIP_EXISTS_DIFFERS):
        result["organize_conflict"] = active_file.name

    if org_result.action == "error":
        print(f"   ❌ Organization failed for {file_path.name}", file=sys.stderr)
        result["failed"] = True
        result["error"] = "Organization failed"
        working_dir.release()
        emit_event("pipeline_result", file=file_path.name, result="failed")
        return result

    # A staged copy organize declined to place is a duplicate of a file already
    # at the destination, so it has no further use. Without this an idempotent
    # re-run stages the whole library into the working dir and leaves it there.
    if org_result.action == "skipped" and working_dir.staged:
        print(f"   Discarded staged copy of {file_path.name} "
              f"(skipped: {org_result.reason})", file=sys.stderr)
        working_dir.discard()

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
    working_dir.release()
    emit_event("stage_complete", stage="output")

    # Generate gyroflow project (if in tasks, enabled, and applying)
    gyroflow_enabled = profile.get("gyroflow_enabled", False) if profile else False
    if tasks and "gyroflow" in tasks and gyroflow_enabled and gyroflow_config:
        print("🎥 Generating gyroflow project...", file=sys.stderr)

        preset = gyroflow_config.get("preset", {})
        preset_json = json.dumps(preset)
        binary = gyroflow_config.get("binary")

        gyroflow_file = Path(dest) if dest and apply else active_file
        gf_result = gyroflow.generate_gyroflow_project(
            gyroflow_file, apply, binary=binary, preset_json=preset_json)
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

    if apply and stats["failed"] > 0:
        print(f"❌ Media pipeline complete - {stats['failed']} file(s) failed and were left in the working directory.", file=sys.stderr)
    elif apply:
        print("✅ Media pipeline complete - changes applied.", file=sys.stderr)
    else:
        print("✅ Media pipeline complete - DRY RUN.", file=sys.stderr)
        print("   Use --apply to execute timestamp fixes and file organization.", file=sys.stderr)


def run(args, working: WorkingDir) -> None:
    """Run the pipeline for parsed command-line arguments; always exits.

    working is the WorkingDir the cancel handler closes over; an apply opens it.
    """
    # Load profile if specified
    profile = None
    full_config = {}
    if args.profile:
        profile, full_config = load_config(args.profile)

    # Apply CLI overrides to profile (workflow tab ad-hoc edits)
    if profile:
        if args.tags is not None:
            profile["tags"] = tagging.parse_tag_list(args.tags)
        if args.make is not None:
            profile.setdefault("exif", {})["make"] = args.make
        if args.model is not None:
            profile.setdefault("exif", {})["model"] = args.model

    extensions = args.extensions or (profile or {}).get("file_extensions")
    if not extensions:
        print("ERROR: no file types to process; declare file_extensions in the profile or pass --extensions", file=sys.stderr)
        sys.exit(1)

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

    try:
        timezone_spec = resolve_timezone(args.timezone, args.location)
    except UnknownTimezone:
        print(f"ERROR: unknown timezone '{args.timezone}' — use an IANA zone name (e.g., Pacific/Auckland) or a +HHMM offset", file=sys.stderr)
        sys.exit(1)
    except UnknownLocation:
        print(f"ERROR: Could not determine timezone for location '{args.location}'", file=sys.stderr)
        sys.exit(1)

    group = args.group

    # Validate --infer-from-filename and --time-offset requirements
    if args.infer_from_filename and not args.timezone:
        print("ERROR: --infer-from-filename requires --timezone", file=sys.stderr)
        sys.exit(1)
    if args.time_offset is not None and not args.timezone:
        print("ERROR: --time-offset requires --timezone", file=sys.stderr)
        sys.exit(1)

    # Check for stale exiftool_tmp directories
    tmp_dirs = check_exiftool_tmp(source_dir)
    if tmp_dirs:
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

    # Set up working directory
    working_dir = args.working_dir or os.path.join(target_dir, WORKING_DIR_NAME)
    working.path = working_dir
    if args.apply:
        working.create()

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

    files = find_media_files(source_dir, extensions)
    total_files = len(files)

    if total_files == 0:
        emit_event("no_media_files", source=source_dir, extensions=list(extensions))
        print(f"No {', '.join(extensions)} files found in {source_dir}", file=sys.stderr)
        sys.exit(0)

    print(f"Found {total_files} {', '.join(extensions)} file(s) to process", file=sys.stderr)
    print(file=sys.stderr)

    protected = [fp.name for fp in files if ingest.is_protected(str(fp))]
    if protected:
        print(f"🔒 {len(protected)} source file(s) are protected (locked):", file=sys.stderr)
        for name in protected:
            print(f"   {name}", file=sys.stderr)
        print("Their imported copies will be unlocked; the source files stay locked.", file=sys.stderr)
        print(file=sys.stderr)
        emit_event("protected_sources", files=protected)
        if args.apply:
            require_consent(args.unlock_protected, "Import them unlocked?", [
                "ERROR: Cannot proceed without consent to import protected files unlocked.",
                "Re-run with --unlock-protected, or from a terminal to be prompted.",
            ])
        else:
            print("Previewing anyway; applying asks first (or pass --unlock-protected).", file=sys.stderr)
            print(file=sys.stderr)

    check_source_camera(files, profile, args.apply, args.allow_camera_mismatch)

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
            working,
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
            if args.source_action == "delete":
                arc_result = archive.delete_files(source_dir, all_source_files, args.apply)
            else:
                arc_result = archive.archive_source(
                    source_dir, args.apply,
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
