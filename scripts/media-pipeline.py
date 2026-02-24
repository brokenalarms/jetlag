#!/usr/bin/env python3
"""
media-pipeline.py
Orchestrates video timestamp fixing and organization into date-based folders.

Usage: media-pipeline.py --profile PROFILE [--subfolder SUBFOLDER] [OPTIONS]
       media-pipeline.py --source DIR --target DIR [--subfolder SUBFOLDER] [OPTIONS]

Processes all video files in SOURCE, fixes timestamps, then organizes by date into TARGET.
"""

import argparse
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path
from typing import Optional

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from lib.exiftool import ExifToolStayOpen
from lib.filesystem import find_media_files

SCRIPT_DIR = Path(__file__).parent


def _import_script(name: str):
    """Import a hyphenated script name as a Python module."""
    path = SCRIPT_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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
    apply: bool,
    et: 'ExifToolStayOpen | None' = None
) -> tuple[str, bool]:
    """Run tag-media.py on a file.

    When et is provided, calls tag-media functions directly (stay_open mode).
    Otherwise falls back to subprocess.

    Returns:
        tuple of (output_text, changed)
    """
    if et:
        import io
        from contextlib import redirect_stdout, redirect_stderr
        tag_media = _import_script("tag-media")

        dry_run = not apply
        finder_tags = tags.split(',') if tags else []
        buf_out = io.StringIO()
        buf_err = io.StringIO()
        changed = False

        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            if make or model:
                success, fields_updated = tag_media.add_camera_to_exif(
                    str(file_path), make=make, model=model, dry_run=dry_run, et=et)
                if fields_updated:
                    changed = True
                    exif_parts = []
                    if 'Make' in fields_updated and make:
                        exif_parts.append(make)
                    if 'Model' in fields_updated and model:
                        exif_parts.append(model)
                    dry_run_suffix = " (DRY RUN)" if dry_run else ""
                    print(f"📌 Tagged: {file_path.name} (EXIF: {' / '.join(exif_parts)}){dry_run_suffix}")

            if finder_tags:
                success, tags_added = tag_media.apply_finder_tags(
                    str(file_path), finder_tags, dry_run=dry_run)
                if tags_added:
                    changed = True

            if not changed:
                dry_run_suffix = " (DRY RUN)" if dry_run else ""
                print(f"✓ {file_path.name}: Already tagged correctly{dry_run_suffix}")

        output = (buf_out.getvalue() + buf_err.getvalue()).strip()
        return output, changed

    cmd = [sys.executable, str(SCRIPT_DIR / "tag-media.py"), str(file_path)]

    if tags:
        cmd.extend(["--tags", tags])
    if make:
        cmd.extend(["--make", make])
    if model:
        cmd.extend(["--model", model])
    if apply:
        cmd.append("--apply")

    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout + result.stderr

    # Check if tags were changed
    changed = False
    if ("📌" in output or "Tagged:" in output or "EXIF:" in output) and "Already tagged correctly" not in output:
        changed = True

    return output.strip(), changed


def run_fix_timestamp(
    file_path: Path,
    location_args: list[str],
    apply: bool,
    verbose: bool,
    et: 'ExifToolStayOpen | None' = None
) -> tuple[str, bool, int]:
    """Run fix-media-timestamp.py on a file.

    When et is provided, calls fix_media_timestamps directly (stay_open mode).
    Otherwise falls back to subprocess.

    Returns:
        tuple of (output_text, changed, return_code)
    """
    if et:
        import io
        from contextlib import redirect_stdout, redirect_stderr
        fmt = _import_script("fix-media-timestamp")

        # Parse location_args to extract timezone/country/flags
        timezone_offset = None
        country = None
        overwrite_dto = False
        preserve_wallclock = False
        i = 0
        while i < len(location_args):
            if location_args[i] == "--timezone" and i + 1 < len(location_args):
                timezone_offset = location_args[i + 1]
                i += 2
            elif location_args[i] == "--country" and i + 1 < len(location_args):
                country = location_args[i + 1]
                i += 2
            elif location_args[i] == "--overwrite-datetimeoriginal":
                overwrite_dto = True
                i += 1
            elif location_args[i] == "--preserve-wallclock-time":
                preserve_wallclock = True
                i += 1
            else:
                i += 1

        if timezone_offset:
            timezone_offset = fmt.normalize_timezone_input(timezone_offset)
        if country and not timezone_offset:
            timezone_offset = fmt.get_timezone_for_country(country)

        buf_out = io.StringIO()
        buf_err = io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            success = fmt.fix_media_timestamps(
                str(file_path),
                dry_run=not apply,
                timezone_offset=timezone_offset,
                overwrite_datetimeoriginal=overwrite_dto,
                preserve_wallclock=preserve_wallclock,
                et=et
            )

        output = (buf_out.getvalue() + buf_err.getvalue()).strip()
        changed = False
        if ("✅" in output or "Updated" in output or "Written" in output) and "No change" not in output:
            changed = True
        if "Change   : " in output and "No change" not in output:
            changed = True

        return output, changed, 0 if success else 1

    cmd = [sys.executable, str(SCRIPT_DIR / "fix-media-timestamp.py"), str(file_path)]
    cmd.extend(location_args)

    if apply:
        cmd.append("--apply")
    if verbose:
        cmd.append("--verbose")

    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout + result.stderr

    # Check if timestamp was changed
    changed = False
    if ("✅" in output or "Updated" in output or "Written" in output) and "No change" not in output:
        changed = True

    return output.strip(), changed, result.returncode


def run_organize_by_date(
    file_path: Path,
    target_dir: str,
    template: str,
    apply: bool,
    verbose: bool,
    et: 'ExifToolStayOpen | None' = None
) -> tuple[str, str, str, int]:
    """Run organize-by-date.py on a file.

    When et is provided, calls organize-by-date functions directly (stay_open mode).
    Otherwise falls back to subprocess.

    Returns:
        tuple of (stderr_output, action, dest_path, return_code)
        action and dest are parsed from @@key=value lines in stdout
    """
    if et:
        import io
        from contextlib import redirect_stderr
        organize_by_date = _import_script("organize-by-date")

        buf_err = io.StringIO()
        with redirect_stderr(buf_err):
            dest, action = organize_by_date.process_file(
                str(file_path), target_dir, template,
                copy_mode=False, overwrite=False,
                apply=apply, verbose=verbose, et=et
            )

        return buf_err.getvalue().strip(), action, dest, 0

    cmd = [
        str(SCRIPT_DIR / "organize-by-date.sh"),
        str(file_path),
        "--target", target_dir,
        "--template", template
    ]

    if apply:
        cmd.append("--apply")
    if verbose:
        cmd.append("--verbose")

    result = subprocess.run(cmd, capture_output=True, text=True)

    # Parse @@key=value from stdout
    action = ""
    dest = ""
    for line in result.stdout.split("\n"):
        if line.startswith("@@action="):
            action = line.split("=", 1)[1]
        elif line.startswith("@@dest="):
            dest = line.split("=", 1)[1]

    # stderr contains user-visible output
    return result.stderr.strip(), action, dest, result.returncode


def run_generate_gyroflow(
    file_path: Path,
    preset_json: str,
    apply: bool
) -> tuple[str, int]:
    """Run generate-gyroflow.py on a file.

    stderr passes through to user. stdout captured for @@key=value parsing.

    Returns:
        tuple of (action, return_code)
        action is parsed from @@action=X in stdout
    """
    cmd = [
        sys.executable, str(SCRIPT_DIR / "generate-gyroflow.py"),
        str(file_path),
        "--preset", preset_json,
    ]

    if apply:
        cmd.append("--apply")

    result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)

    action = ""
    for line in result.stdout.split("\n"):
        if line.startswith("@@action="):
            action = line.split("=", 1)[1]

    return action, result.returncode


def process_file(
    file_path: Path,
    profile: Optional[dict],
    target_dir: str,
    subfolder: Optional[str],
    location_args: list[str],
    apply: bool,
    verbose: bool,
    gyroflow_config: Optional[dict] = None,
    tasks: Optional[set] = None,
    et: 'ExifToolStayOpen | None' = None
) -> dict:
    """Process a single file through the pipeline.

    Returns:
        dict with keys: changed, failed, error
    """
    result = {"changed": False, "failed": False, "error": None}
    file_changed = False

    # Step 1: Tag media (if profile has tags/make/model)
    if (tasks is None or "tag" in tasks) and profile:
        tags = ",".join(profile.get("tags", []))
        exif = profile.get("exif", {})
        make = exif.get("make", "")
        model = exif.get("model", "")

        if tags or make or model:
            print("🏷️  Checking tags...")
            output, changed = run_tag_media(file_path, tags or None, make or None, model or None, apply, et=et)
            for line in output.split("\n"):
                print(f"  {line}")
            if changed:
                file_changed = True

    # Step 2: Fix video timestamp
    if tasks is None or "fix-timestamp" in tasks:
        print("🔧 Fixing timestamp...")
        output, changed, rc = run_fix_timestamp(file_path, location_args, apply, verbose, et=et)
        for line in output.split("\n"):
            print(f"  {line}")

        if rc != 0:
            print(f"   ❌ Timestamp fix failed for {file_path.name}")
            result["failed"] = True
            result["error"] = "Timestamp fix failed"
            return result

        if changed:
            file_changed = True

    # Step 3: Organize by date
    dest = ""
    if tasks is None or "organize" in tasks:
        print("📁 Organizing by date...")

        folder_template = profile.get("folder_template") if profile else None
        if folder_template:
            template = folder_template.replace("{{SUBFOLDER}}", subfolder) if subfolder else folder_template
        elif subfolder:
            template = f"{{{{YYYY}}}}/{subfolder}/{{{{YYYY}}}}-{{{{MM}}}}-{{{{DD}}}}"
        else:
            template = "{{YYYY}}/{{YYYY}}-{{MM}}-{{DD}}"
        output, action, dest, rc = run_organize_by_date(file_path, target_dir, template, apply, verbose, et=et)

        # Print stderr output (user-visible messages)
        if output:
            for line in output.split("\n"):
                if line.strip():
                    print(line)

        if rc != 0:
            print(f"   ❌ Organization failed for {file_path.name}")
            result["failed"] = True
            result["error"] = "Organization failed"
            return result

        if action in ("copied", "moved", "overwrote"):
            file_changed = True

    # Step 4: Generate gyroflow project (if enabled)
    gyroflow_enabled = profile.get("gyroflow_enabled", False) if profile else False
    if (tasks is None or "gyroflow" in tasks) and gyroflow_enabled and gyroflow_config:
        print("🎥 Generating gyroflow project...")

        # Use the dest path from organize (file may have moved)
        gyroflow_file = Path(dest) if dest else file_path
        preset = gyroflow_config.get("preset", {})
        preset_json = json.dumps(preset)

        gf_action, rc = run_generate_gyroflow(gyroflow_file, preset_json, apply)

        if rc != 0:
            print(f"   ⚠️  Gyroflow generation failed for {file_path.name} (non-fatal)")
        elif gf_action == "generated":
            file_changed = True

    result["changed"] = file_changed
    return result


def print_summary(stats: dict, apply: bool):
    """Print pipeline summary."""
    print()
    print("===========================================")
    print("📊 MEDIA PIPELINE SUMMARY")
    print("-------------------------------------------")
    print(f"Total files processed: {stats['processed']}")
    print(f"Successfully completed: {stats['succeeded']}")
    print(f"Files changed: {stats['changed']}")
    print(f"Files unchanged: {stats['succeeded'] - stats['changed']}")

    if stats["failed"] > 0:
        print(f"Failed: {stats['failed']}")
        print()
        print("Failed files:")
        for f in stats["failed_files"]:
            print(f"  - {f}")

    if apply:
        print("✅ Media pipeline complete - changes applied.")
    else:
        print("✅ Media pipeline complete - DRY RUN.")
        print("   Use --apply to execute timestamp fixes and file organization.")


def main():
    """Main entry point."""
    # Set up signal handler for Ctrl-C
    signal.signal(signal.SIGINT, signal_handler)

    parser = argparse.ArgumentParser(
        description="Orchestrates video timestamp fixing and organization into date-based folders."
    )
    parser.add_argument("--profile", help="Profile from media-profiles.yaml")
    parser.add_argument("--source", help="Directory containing video files (default: current directory)")
    parser.add_argument("--target", help="Target directory for organized files")
    parser.add_argument("--location", help="Location name/code for timezone lookup")
    parser.add_argument("--timezone", help="Timezone in +HHMM format (e.g., +0800)")
    parser.add_argument("--subfolder", help="Optional subfolder name substituted for {{SUBFOLDER}} in the profile's folder_template, or inserted between year and date by default (e.g., 'Japan Trip' → YYYY/Japan Trip/YYYY-MM-DD)")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default: dry run)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed processing info")
    parser.add_argument(
        "--tasks", nargs="+",
        choices=["tag", "fix-timestamp", "organize", "gyroflow"],
        help="Pipeline steps to run (default: all)"
    )

    args = parser.parse_args()

    # Load profile if specified
    profile = None
    full_config = {}
    if args.profile:
        profile, full_config = load_config(args.profile)

    # Determine source and target directories from profile or CLI args
    source_dir = args.source
    target_dir = args.target

    if profile:
        import_dir = profile.get("import_dir")
        ready_dir = profile.get("ready_dir")
        if not source_dir and import_dir and import_dir != "None":
            source_dir = import_dir
        if not target_dir and ready_dir and ready_dir != "None":
            target_dir = ready_dir

    if not source_dir:
        print("ERROR: --source is required (or use --profile with import_dir)", file=sys.stderr)
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

    # Build location args for child scripts
    location_args = []
    if args.location:
        location_args = ["--location", args.location]
    elif args.timezone:
        location_args = ["--timezone", args.timezone]

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
                    import shutil
                    shutil.rmtree(d)
                print("✅ Deleted exiftool_tmp directories", file=sys.stderr)
            else:
                print("ERROR: Cannot proceed - exiftool will fail with these directories present", file=sys.stderr)
                sys.exit(1)
        except EOFError:
            print("ERROR: Cannot proceed - exiftool will fail with these directories present", file=sys.stderr)
            sys.exit(1)

    # Display configuration
    print(f"→ Source:  {source_dir}")
    print(f"→ Target:  {target_dir}")
    print(f"→ Mode:    {'APPLY (files will be processed)' if args.apply else 'DRY RUN (no changes)'}")
    if location_args:
        print(f"→ Timezone: {location_args[0]} {location_args[1]}")
    else:
        print("→ Timezone: From video metadata (or will prompt if needed)")
    print()

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
        print(f"No video files found in {source_dir}")
        sys.exit(0)

    print(f"📹 Found {total_files} video file(s) to process")
    print()

    # Process each file
    stats = {
        "processed": 0,
        "succeeded": 0,
        "changed": 0,
        "failed": 0,
        "failed_files": []
    }

    gyroflow_config = full_config.get("gyroflow")
    tasks = set(args.tasks) if args.tasks else None

    with ExifToolStayOpen() as et:
        for i, file_path in enumerate(files, 1):
            stats["processed"] += 1
            base = file_path.name

            print(f"[{i}/{total_files}] Processing: {base}")

            result = process_file(
                file_path,
                profile,
                target_dir,
                args.subfolder,
                location_args,
                args.apply,
                args.verbose,
                gyroflow_config=gyroflow_config,
                tasks=tasks,
                et=et
            )

            if result["failed"]:
                stats["failed"] += 1
                stats["failed_files"].append(base)
            else:
                stats["succeeded"] += 1
                if result["changed"]:
                    stats["changed"] += 1

            print()  # Empty line between files

    # Print summary
    print_summary(stats, args.apply)

    # Exit with error if any files failed
    sys.exit(1 if stats["failed"] > 0 else 0)


if __name__ == "__main__":
    main()
