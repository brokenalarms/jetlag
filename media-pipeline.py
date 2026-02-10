#!/usr/bin/env python3
"""
media-pipeline.py
Orchestrates video timestamp fixing and organization into date-based folders.

Usage: media-pipeline.py --profile PROFILE --group GROUP [OPTIONS]
       media-pipeline.py --source DIR --target DIR --group GROUP [OPTIONS]

Processes all video files in SOURCE, fixes timestamps, then organizes by date into TARGET.
"""

import argparse
import os
import re
import signal
import subprocess
import sys
from pathlib import Path
from typing import Optional

import yaml


SCRIPT_DIR = Path(__file__).parent


def signal_handler(sig, frame):
    """Handle Ctrl-C gracefully."""
    print("\n\nInterrupted by user", file=sys.stderr)
    sys.exit(130)


def load_profile(profile_name: str) -> dict:
    """Load profile from media-profiles.yaml."""
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

    return profiles[profile_name]


def find_media_files(source_dir: str, extensions: list[str]) -> list[Path]:
    """Find all media files with given extensions, sorted alphabetically."""
    source = Path(source_dir)
    files = []

    for ext in extensions:
        # Case-insensitive matching
        files.extend(source.rglob(f"*{ext}"))
        files.extend(source.rglob(f"*{ext.upper()}"))

    # Remove duplicates and sort
    unique_files = list(set(files))
    unique_files.sort(key=lambda p: str(p).lower())

    return unique_files


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
) -> tuple[str, str, int]:
    """Run organize-by-date.py on a file.

    Returns:
        tuple of (stderr_output, action, return_code)
        action is parsed from @@action=X in stdout
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
    for line in result.stdout.split("\n"):
        if line.startswith("@@action="):
            action = line.split("=", 1)[1]

    # stderr contains user-visible output
    return result.stderr.strip(), action, result.returncode


def process_file(
    file_path: Path,
    profile: Optional[dict],
    target_dir: str,
    group: str,
    location_args: list[str],
    apply: bool,
    verbose: bool
) -> dict:
    """Process a single file through the pipeline.

    Returns:
        dict with keys: changed, failed, error
    """
    result = {"changed": False, "failed": False, "error": None}
    file_changed = False

    # Step 1: Tag media (if profile has tags/make/model)
    if profile:
        tags = ",".join(profile.get("tags", []))
        exif = profile.get("exif", {})
        make = exif.get("make", "")
        model = exif.get("model", "")

        if tags or make or model:
            print("🏷️  Checking tags...")
            output, changed = run_tag_media(file_path, tags or None, make or None, model or None, apply)
            for line in output.split("\n"):
                print(f"  {line}")
            if changed:
                file_changed = True

    # Step 2: Fix video timestamp
    print("🔧 Fixing timestamp...")
    output, changed, rc = run_fix_timestamp(file_path, location_args, apply, verbose)
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
    print("📁 Organizing by date...")

    template = f"{{{{YYYY}}}}/{group}/{{{{YYYY}}}}-{{{{MM}}}}-{{{{DD}}}}"
    output, action, rc = run_organize_by_date(file_path, target_dir, template, apply, verbose)

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
    parser.add_argument("--group", help="Group name for organizing dates (required)")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default: dry run)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed processing info")

    args = parser.parse_args()

    # Load profile if specified
    profile = None
    if args.profile:
        profile = load_profile(args.profile)

    # Determine source and target directories from profile or CLI args
    source_dir = args.source
    target_dir = args.target

    if profile:
        ready_dir = profile.get("ready_dir")
        if ready_dir and ready_dir != "None":
            if not source_dir:
                source_dir = ready_dir
            if not target_dir:
                target_dir = ready_dir

    if not source_dir:
        print("ERROR: --source is required (or use --profile with ready_dir)", file=sys.stderr)
        sys.exit(1)

    if not target_dir:
        print("ERROR: --target is required (or use --profile with ready_dir)", file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(source_dir):
        print(f"ERROR: Source directory not found: {source_dir}", file=sys.stderr)
        sys.exit(1)

    # Validate group is provided
    if not args.group:
        print("ERROR: --group is required", file=sys.stderr)
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

    for i, file_path in enumerate(files, 1):
        stats["processed"] += 1
        base = file_path.name

        print(f"[{i}/{total_files}] Processing: {base}")

        result = process_file(
            file_path,
            profile,
            target_dir,
            args.group,
            location_args,
            args.apply,
            args.verbose
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
