#!/usr/bin/env python3
"""
media-pipeline.py
Orchestrates video timestamp fixing and organization into date-based folders.

Usage: media-pipeline.py --profile PROFILE [--subfolder SUBFOLDER] [OPTIONS]
       media-pipeline.py --source DIR --target DIR [--subfolder SUBFOLDER] [OPTIONS]

Processes all video files in SOURCE, fixes timestamps, then organizes by date into TARGET.
"""

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from lib.filesystem import find_companions, find_media_files

SCRIPT_DIR = Path(__file__).parent


def copy_to_working_dir(source_file: Path, working_dir: str) -> Path:
    """Copy a file into the working directory (flat, no subdirectories).

    Returns:
        Path to the copied file in the working directory
    """
    os.makedirs(working_dir, exist_ok=True)
    dest = Path(working_dir) / source_file.name
    shutil.copy2(str(source_file), str(dest))
    return dest


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
) -> tuple[str, bool]:
    """Run tag-media.py on a file.

    Returns:
        tuple of (output_text, changed)
    """
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
    verbose: bool
) -> tuple[str, bool, int]:
    """Run fix-media-timestamp.py on a file.

    Returns:
        tuple of (output_text, changed, return_code)
    """
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
    verbose: bool
) -> tuple[str, str, str, int]:
    """Run organize-by-date.py on a file.

    Returns:
        tuple of (stderr_output, action, dest_path, return_code)
        action and dest are parsed from @@key=value lines in stdout
    """
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
    working_dir: str,
    gyroflow_config: Optional[dict] = None,
    tasks: Optional[set] = None
) -> dict:
    """Process a single file through the pipeline.

    Pipeline flow: ingest (always) → [tag] → [fix-timestamp] → output (always) → [gyroflow]
    Ingest copies source to temp working dir. Output organizes to ready_dir.

    Returns:
        dict with keys: changed, failed, error, working_copy, dest_path
    """
    result = {"changed": False, "failed": False, "error": None, "working_copy": None, "dest_path": None}
    file_changed = False

    # Step 0: Ingest — copy source to working directory (always)
    if apply:
        working_copy = copy_to_working_dir(file_path, working_dir)
        print("  📥 Copied to working directory")
    else:
        working_copy = file_path
        print("  📥 Would copy to working directory")
    result["working_copy"] = working_copy

    # Step 1: Tag media (if in tasks and profile has tags/make/model)
    if (tasks is None or "tag" in tasks) and profile:
        tags = ",".join(profile.get("tags", []))
        exif = profile.get("exif", {})
        make = exif.get("make", "")
        model = exif.get("model", "")

        if tags or make or model:
            print("🏷️  Checking tags...")
            output, changed = run_tag_media(working_copy, tags or None, make or None, model or None, apply)
            for line in output.split("\n"):
                print(f"  {line}")
            if changed:
                file_changed = True

    # Step 2: Fix timestamp
    if tasks is None or "fix-timestamp" in tasks:
        print("🔧 Fixing timestamp...")
        output, changed, rc = run_fix_timestamp(working_copy, location_args, apply, verbose)
        for line in output.split("\n"):
            print(f"  {line}")

        if rc != 0:
            print(f"   ❌ Timestamp fix failed for {file_path.name}")
            result["failed"] = True
            result["error"] = "Timestamp fix failed"
            return result

        if changed:
            file_changed = True

    # Step 3: Output — organize to ready_dir (always runs)
    print("📁 Organizing by date...")

    folder_template = profile.get("folder_template") if profile else None
    if folder_template:
        template = folder_template.replace("{{SUBFOLDER}}", subfolder) if subfolder else folder_template
    elif subfolder:
        template = f"{{{{YYYY}}}}/{subfolder}/{{{{YYYY}}}}-{{{{MM}}}}-{{{{DD}}}}"
    else:
        template = "{{YYYY}}/{{YYYY}}-{{MM}}-{{DD}}"
    output, action, dest, rc = run_organize_by_date(working_copy, target_dir, template, apply, verbose)

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

    result["dest_path"] = dest

    # Step 4: Generate gyroflow project (if enabled, operates on file in ready_dir)
    gyroflow_enabled = profile.get("gyroflow_enabled", False) if profile else False
    if (tasks is None or "gyroflow" in tasks) and gyroflow_enabled and gyroflow_config:
        print("🎥 Generating gyroflow project...")

        gyroflow_file = Path(dest) if dest else working_copy
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
        choices=["tag", "fix-timestamp", "gyroflow", "archive-source"],
        default=["tag", "fix-timestamp", "gyroflow"],
        help="Optional processing steps to run (default: tag fix-timestamp gyroflow)"
    )
    parser.add_argument(
        "--copy-companion-files", action="store_true",
        help="Copy companion files (e.g., .lrv, .thm) to target alongside main files"
    )
    parser.add_argument(
        "--source-action",
        choices=["leave", "archive", "delete"],
        default="leave",
        help="Action for archive-source task (default: leave)"
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
        ready_dir = profile.get("ready_dir")
        profile_source = profile.get("source_dir")
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

    # Create temp working directory
    working_dir = tempfile.mkdtemp(prefix="jetlag-pipeline-")

    # Process each file
    stats = {
        "processed": 0,
        "succeeded": 0,
        "changed": 0,
        "failed": 0,
        "failed_files": []
    }

    gyroflow_config = full_config.get("gyroflow")
    tasks = set(args.tasks) if args.tasks else set()
    pipeline_failed = False

    # Track all processed source paths (main files + companions) for archive-source
    processed_source_paths = []

    # Get companion extensions from profile
    companion_extensions = profile.get("companion_extensions", []) if profile else []

    try:
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
                working_dir,
                gyroflow_config=gyroflow_config,
                tasks=tasks
            )

            if result["failed"]:
                stats["failed"] += 1
                stats["failed_files"].append(base)
                pipeline_failed = True
            else:
                stats["succeeded"] += 1
                if result["changed"]:
                    stats["changed"] += 1
                processed_source_paths.append(str(file_path))

                # Copy companion files if requested (ingest → output only, skip processing steps)
                if args.copy_companion_files and companion_extensions:
                    companions = find_companions(file_path, companion_extensions)
                    for companion in companions:
                        print(f"  📎 Companion: {companion.name}")
                        if args.apply:
                            companion_working = copy_to_working_dir(companion, working_dir)
                            # Output: organize companion to ready_dir (same template as main file)
                            folder_template = profile.get("folder_template") if profile else None
                            if folder_template:
                                template = folder_template.replace("{{SUBFOLDER}}", args.subfolder) if args.subfolder else folder_template
                            elif args.subfolder:
                                template = f"{{{{YYYY}}}}/{args.subfolder}/{{{{YYYY}}}}-{{{{MM}}}}-{{{{DD}}}}"
                            else:
                                template = "{{YYYY}}/{{YYYY}}-{{MM}}-{{DD}}"
                            c_output, c_action, c_dest, c_rc = run_organize_by_date(
                                companion_working, target_dir, template, True, args.verbose
                            )
                            if c_output:
                                for line in c_output.split("\n"):
                                    if line.strip():
                                        print(f"    {line}")
                        else:
                            print(f"    Would copy to target")
                        processed_source_paths.append(str(companion))

            print()  # Empty line between files
    except Exception:
        pipeline_failed = True
        raise
    finally:
        # Clean up working directory
        if pipeline_failed:
            print(f"Working directory preserved for inspection: {working_dir}", file=sys.stderr)
        else:
            try:
                os.rmdir(working_dir)
            except FileNotFoundError:
                pass
            except OSError:
                if not args.apply:
                    shutil.rmtree(working_dir, ignore_errors=True)
                else:
                    print(f"Working directory not empty (some files may not have been organized): {working_dir}", file=sys.stderr)

    # Archive-source: act on source directory after all files processed
    if "archive-source" in tasks and not pipeline_failed:
        print("📦 Running archive-source...")
        archive_cmd = [
            sys.executable, str(SCRIPT_DIR / "archive-source.py"),
            "--source", source_dir,
            "--action", args.source_action,
        ]
        if processed_source_paths:
            archive_cmd.append("--files")
            archive_cmd.extend(processed_source_paths)
        if args.apply:
            archive_cmd.append("--apply")

        archive_result = subprocess.run(archive_cmd, capture_output=False)
        if archive_result.returncode != 0:
            print(f"  ⚠️  archive-source failed (exit {archive_result.returncode})")

    # Print summary
    print_summary(stats, args.apply)

    # Exit with error if any files failed
    sys.exit(1 if stats["failed"] > 0 else 0)


if __name__ == "__main__":
    main()
