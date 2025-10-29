#!/usr/bin/env python3
"""
Media import script with profile-based configuration
Imports media files from source directories to organized destinations with date-based folders
"""

import subprocess
import sys
import os
import signal
import json
import yaml
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, NamedTuple
import argparse

# Handle Ctrl-C gracefully
def signal_handler(sig, frame):
    print("\n\nInterrupted by user", file=sys.stderr)
    sys.exit(130)

signal.signal(signal.SIGINT, signal_handler)

class ImportProfile(NamedTuple):
    """Configuration profile for media import"""
    import_dir: str
    companion_extensions: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    exif_make: Optional[str] = None
    exif_model: Optional[str] = None

class ImportResult(NamedTuple):
    """Result of importing a single file"""
    success: bool
    action: str  # "copied", "skipped", "failed"
    source_path: str
    dest_path: Optional[str] = None
    error: Optional[str] = None

def load_profiles(profile_path: str) -> Dict[str, ImportProfile]:
    """Load import profiles from YAML or JSON file"""
    try:
        with open(profile_path, 'r') as f:
            if profile_path.endswith('.yaml') or profile_path.endswith('.yml'):
                data = yaml.safe_load(f)
            else:
                data = json.load(f)

        profiles = {}
        for name, config in data.get('profiles', data).items():
            exif = config.get('exif', {})
            profiles[name] = ImportProfile(
                import_dir=os.path.expandvars(config['import_dir']),
                companion_extensions=config.get('companion_extensions'),
                tags=config.get('tags'),
                exif_make=exif.get('make'),
                exif_model=exif.get('model')
            )
        return profiles
    except Exception as e:
        print(f"Error loading profiles from {profile_path}: {e}", file=sys.stderr)
        return {}

def get_default_profile_path() -> str:
    """Get default profile file path"""
    script_dir = Path(__file__).parent
    for filename in ['media-profiles.yaml', 'media-profiles.yml', 'media-profiles.json']:
        profile_path = script_dir / filename
        if profile_path.exists():
            return str(profile_path)
    return str(script_dir / 'media-profiles.yaml')

def compute_destination_path(file_path: str, import_dir: str) -> Optional[str]:
    """Compute the expected destination path for a file based on its DateTimeOriginal

    This replicates the logic from organize-by-date.sh using get_file_date_for_organization
    """
    try:
        # Get file date (YYYY-MM-DD format)
        result = subprocess.run(
            ['exiftool', '-fast2', '-s', '-DateTimeOriginal', file_path],
            capture_output=True, text=True, check=True
        )

        file_date = None
        for line in result.stdout.strip().split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                if key.strip() == 'DateTimeOriginal':
                    dt_str = value.strip()
                    if dt_str:
                        # Extract date part and convert YYYY:MM:DD → YYYY-MM-DD
                        date_part = dt_str.split(' ')[0]
                        file_date = date_part.replace(':', '-')
                        break

        if not file_date:
            # Fallback to file modification time
            from datetime import datetime
            mtime = os.path.getmtime(file_path)
            file_date = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')

        # Expand template: {{YYYY}}/{{YYYY}}-{{MM}}-{{DD}} (default template)
        year, month, day = file_date.split('-')
        organized_path = f"{year}/{file_date}"

        # Construct full destination path
        filename = os.path.basename(file_path)
        dest_path = os.path.join(import_dir, organized_path, filename)

        return dest_path

    except Exception:
        return None

def organize_file(file_path: str, import_dir: str, copy_mode: bool = True, apply_changes: bool = False) -> ImportResult:
    """Organize a single file using organize-by-date.sh"""
    script_dir = Path(__file__).parent
    organize_script = script_dir / 'organize-by-date.sh'

    cmd = [str(organize_script), file_path, '--target', import_dir]
    if copy_mode:
        cmd.append('--copy')
    if apply_changes:
        cmd.append('--apply')

    try:
        # Let output pass through naturally for owned scripts
        result = subprocess.run(cmd, text=True, check=True)

        action = "copied" if apply_changes else "would_copy"

        # Compute destination path only when needed (for tagging after copy)
        # Don't waste time during dry run since we don't tag in dry run mode
        dest_path = compute_destination_path(file_path, import_dir) if apply_changes else None

        return ImportResult(True, action, file_path, dest_path=dest_path)

    except subprocess.CalledProcessError as e:
        # Errors already displayed by subprocess
        return ImportResult(False, "failed", file_path, error=None)

def tag_file(file_path: str, tags: Optional[List[str]] = None, make: Optional[str] = None, model: Optional[str] = None, apply_changes: bool = False) -> bool:
    """Tag a file using tag-media.py script"""
    if not tags and not make and not model:
        return True

    script_dir = Path(__file__).parent
    tag_script = script_dir / 'tag-media.py'

    cmd = [str(tag_script), file_path]
    if tags:
        cmd.extend(['--tags', ','.join(tags)])
    if make:
        cmd.extend(['--make', make])
    if model:
        cmd.extend(['--model', model])
    if apply_changes:
        cmd.append('--apply')

    try:
        subprocess.run(cmd, text=True, check=True)
        return True
    except subprocess.CalledProcessError:
        # Error already displayed by tag-media.py
        return False

def find_source_directory(specified_dir: Optional[str]) -> str:
    """Find source directory - either specified or auto-detect single unprocessed directory"""
    if specified_dir:
        if not os.path.isdir(specified_dir):
            raise ValueError(f"Directory '{specified_dir}' not found")
        return specified_dir

    # Look for single unprocessed subdirectory
    current_dir = Path.cwd()
    candidates = []

    for item in current_dir.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            # Skip already processed directories
            if '- copied' not in item.name:
                candidates.append(str(item))

    if len(candidates) == 0:
        raise ValueError("No unprocessed subdirectories found in current directory")
    elif len(candidates) > 1:
        raise ValueError(f"Multiple subdirectories found. Please specify which one:\n" +
                        '\n'.join(f"  {os.path.basename(c)}" for c in candidates))

    return candidates[0]

def get_media_files(directory: str, include_companion: bool = True, companion_extensions: Optional[List[str]] = None) -> List[str]:
    """Get all media files from directory, excluding system files"""
    media_files = []

    # Default companion extensions (GoPro and DJI)
    if companion_extensions is None:
        companion_extensions = ['.lrv', '.thm', '.lrf']

    # Convert to lowercase set for faster lookup
    companion_exts = {ext.lower() for ext in companion_extensions}

    for root, _, files in os.walk(directory):
        for file in files:
            if file.startswith('.') or file in ['.DS_Store', 'Thumbs.db']:
                continue

            # Skip companion files if not wanted
            if not include_companion:
                file_ext = Path(file).suffix.lower()
                if file_ext in companion_exts:
                    continue

            media_files.append(os.path.join(root, file))
    return sorted(media_files)

def find_companion_files(main_file_path: str, companion_extensions: Optional[List[str]] = None) -> List[str]:
    """Find all companion files for a given main file (e.g., IMG_001.LRV for IMG_001.MP4)"""
    if companion_extensions is None:
        companion_extensions = ['.lrv', '.thm', '.lrf']

    companion_exts = {ext.lower() for ext in companion_extensions}
    base_path = Path(main_file_path)
    base_name = base_path.stem  # filename without extension
    parent_dir = base_path.parent

    companions = []
    for ext in companion_exts:
        companion_path = parent_dir / f"{base_name}{ext}"
        if companion_path.exists():
            companions.append(str(companion_path))
        # Also check uppercase extension
        companion_path_upper = parent_dir / f"{base_name}{ext.upper()}"
        if companion_path_upper.exists():
            companions.append(str(companion_path_upper))

    return companions

def create_archive_directory(original_dir: str, apply_changes: bool) -> Optional[str]:
    """Create archive directory for processed files"""
    if not apply_changes:
        return None

    current_date = datetime.now().strftime('%Y-%m-%d')
    archive_name = f"{os.path.basename(original_dir)} - copied {current_date}"
    archive_path = os.path.join(os.path.dirname(original_dir), archive_name)

    os.makedirs(archive_path, exist_ok=True)
    return archive_path

def cleanup_empty_parent_dirs(file_dir: str, source_root: str) -> None:
    """Clean up empty parent directories after moving a file

    Keep removing parent directories as long as they're empty.
    Stop at source_root or when we hit a non-empty directory.
    """
    import errno

    while file_dir and file_dir != source_root and file_dir != '/' and file_dir != '.':
        try:
            # Try to remove the directory (only succeeds if empty)
            os.rmdir(file_dir)
            # Move up to parent
            file_dir = os.path.dirname(file_dir)
        except OSError as e:
            # Directory not empty - expected, stop here
            if e.errno == errno.ENOTEMPTY or e.errno == errno.EEXIST:
                break
            # Other errors (permissions, etc) - warn but stop
            print(f"Warning: Could not remove empty directory {file_dir}: {e}", file=sys.stderr)
            break

def archive_processed_file(file_path: str, source_dir: str, archive_dir: Optional[str]) -> bool:
    """Move processed file to archive directory, preserving relative directory structure"""
    if not archive_dir:
        return True

    try:
        # Save the directory before moving the file
        source_file_dir = os.path.dirname(file_path)

        # Preserve directory structure relative to source_dir
        rel_path = os.path.relpath(file_path, source_dir)
        archive_file_path = os.path.join(archive_dir, rel_path)

        # Create parent directories if needed
        os.makedirs(os.path.dirname(archive_file_path), exist_ok=True)

        shutil.move(file_path, archive_file_path)

        # Clean up empty parent directories after moving
        cleanup_empty_parent_dirs(source_file_dir, source_dir)

        return True
    except Exception as e:
        print(f"Warning: Failed to archive {file_path}: {e}", file=sys.stderr)
        return False

def cleanup_empty_directory(directory: str) -> None:
    """Remove original directory if empty after processing"""
    try:
        # Check if directory is empty (ignoring hidden files)
        remaining_files = get_media_files(directory)
        if not remaining_files:
            os.rmdir(directory)
            print(f"Removed empty directory: {os.path.basename(directory)}")
        else:
            print(f"⚠️  Original folder '{os.path.basename(directory)}' still contains {len(remaining_files)} file(s)")
    except OSError as e:
        print(f"Note: Could not remove directory {directory}: {e}")

def format_import_summary(results: List[ImportResult], archive_dir: Optional[str]) -> str:
    """Format import summary from results"""
    copied = sum(1 for r in results if r.action == "copied")
    skipped = sum(1 for r in results if r.action == "skipped")
    failed = sum(1 for r in results if r.action == "failed")

    lines = []
    if copied > 0:
        lines.append(f"   - Copied: {copied} file(s)")
    if skipped > 0:
        lines.append(f"   - Skipped: {skipped} file(s) (already exist)")
    if failed > 0:
        lines.append(f"   - Failed: {failed} file(s)")
    if archive_dir:
        lines.append(f"   - Archived to: {os.path.basename(archive_dir)}")

    return '\n'.join(lines)

def import_media(source_dir: str, profile: ImportProfile,
                 apply_changes: bool = False, skip_companion: bool = False) -> tuple[List[ImportResult], Optional[str], List[str]]:
    """Main import function - processes all files in source directory

    Returns: (results, archive_dir, companion_files_to_archive)
    """

    # Get files to import (may exclude companions)
    import_files = get_media_files(source_dir, include_companion=not skip_companion, companion_extensions=profile.companion_extensions)

    # Get ALL files for archiving (capture this BEFORE we start moving files)
    all_files = get_media_files(source_dir, include_companion=True, companion_extensions=profile.companion_extensions)

    # Calculate which files won't be imported but need archiving
    import_files_set = set(import_files)
    companion_files_to_archive = [f for f in all_files if f not in import_files_set]

    if not import_files:
        print("No media files found to process")
        return [], None, []

    if skip_companion:
        companion_count = len(companion_files_to_archive)
        print(f"Found {len(import_files)} file(s) to import ({companion_count} companion files will be archived only)")
    else:
        print(f"Found {len(import_files)} file(s) to process")
    print()

    # Process files for import
    results = []
    archive_dir = None

    for i, file_path in enumerate(import_files, 1):
        filename = os.path.basename(file_path)

        if apply_changes:
            print(f"[{i}/{len(import_files)}] Processing: {filename}")

        # Organize the file (copy to destination)
        result = organize_file(file_path, profile.import_dir, copy_mode=True, apply_changes=apply_changes)
        results.append(result)

        if not result.success:
            # Error already displayed by organize-by-date.sh
            continue

        # ALWAYS tag the DESTINATION file after organizing (whether or not profile has tags)
        # This ensures tagging happens AFTER copy/move, never before (much faster than tagging on memory card)
        if apply_changes and result.dest_path and os.path.exists(result.dest_path):
            if not tag_file(result.dest_path, tags=profile.tags, make=profile.exif_make, model=profile.exif_model, apply_changes=apply_changes):
                print(f"   Warning: Tagging failed for {filename}")

        # For successful copies in apply mode, archive the source file immediately
        # This ensures progress is preserved in case of interruption
        if apply_changes and result.action == "copied":
            # Create archive directory on first successful copy
            if not archive_dir:
                archive_dir = create_archive_directory(source_dir, apply_changes)
                if archive_dir:
                    print(f"Created archive folder: {os.path.basename(archive_dir)}")

            # Archive this file and its companions immediately (not at the end)
            if archive_dir:
                archive_processed_file(file_path, source_dir, archive_dir)

                # Also archive companion files for this main file
                companion_files = find_companion_files(file_path, profile.companion_extensions)
                for companion_path in companion_files:
                    if os.path.exists(companion_path):
                        archive_processed_file(companion_path, source_dir, archive_dir)

    return results, archive_dir, companion_files_to_archive

def main():
    """Command line interface"""
    parser = argparse.ArgumentParser(
        description='Import media files with profile-based configuration',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --profile insta360 --apply
  %(prog)s --profile gopro DCIM --apply
  %(prog)s --profile gopro DCIM --skip-companion --apply
        """
    )

    parser.add_argument('source_dir', nargs='?',
                       help='Source directory (auto-detected if only one subdirectory exists)')
    parser.add_argument('--profile',
                       help='Profile name from configuration file')
    parser.add_argument('--skip-companion', action='store_true',
                       help='Skip companion files (.lrv, .thm) - saves space, recommended for FCP workflows')
    parser.add_argument('--profiles-file',
                       help='Path to profiles configuration file')
    parser.add_argument('--apply', action='store_true',
                       help='Apply changes (default: dry run)')
    parser.add_argument('--list-profiles', action='store_true',
                       help='List available profiles and exit')

    args = parser.parse_args()

    # Load profiles
    profiles_file = args.profiles_file or get_default_profile_path()
    profiles = load_profiles(profiles_file)

    if args.list_profiles:
        if profiles:
            print("Available profiles:")
            for name, profile in profiles.items():
                print(f"  {name:12} → {profile.import_dir}")
        else:
            print("No profiles found")
            print(f"Create a profiles file at: {profiles_file}")
        return 0

    # Load profile
    if not args.profile:
        print("Error: --profile is required", file=sys.stderr)
        print("Use --list-profiles to see available profiles", file=sys.stderr)
        return 1

    if args.profile not in profiles:
        print(f"Error: Profile '{args.profile}' not found", file=sys.stderr)
        print(f"Available profiles: {', '.join(profiles.keys())}", file=sys.stderr)
        return 1

    profile = profiles[args.profile]

    # Find source directory
    try:
        source_dir = find_source_directory(args.source_dir)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Check if already processed
    if '- copied' in os.path.basename(source_dir):
        response = input(f"Directory '{os.path.basename(source_dir)}' appears already processed. Continue? (y/N) ")
        if not response.lower().startswith('y'):
            return 0

    # Display configuration
    print(f"→ Source:      {source_dir}")
    print(f"→ Import target: {profile.import_dir}")
    print(f"→ Mode:        {'APPLY' if args.apply else 'DRY RUN (no changes)'}")
    print()

    # Import media
    results, archive_dir, companion_files = import_media(
        source_dir, profile,
        apply_changes=args.apply,
        skip_companion=args.skip_companion
    )

    if not results:
        return 0

    print()

    # Handle post-processing for apply mode
    if args.apply:
        copied_count = sum(1 for r in results if r.action == "copied")

        if copied_count > 0 and archive_dir:
            # Check for orphaned companion files (shouldn't normally happen)
            orphaned_companions = []
            for file_path in companion_files:
                if os.path.exists(file_path):
                    orphaned_companions.append(file_path)

            if orphaned_companions:
                print(f"\n⚠️  Warning: Found {len(orphaned_companions)} orphaned companion file(s):")
                print("   These companion files don't have a matching main file that was imported.")
                for orphan in orphaned_companions:
                    print(f"   - {os.path.basename(orphan)}")

                response = input("\nArchive these orphaned files? (y/N) ")
                if response.lower().startswith('y'):
                    print("Archiving orphaned companion files...")
                    for file_path in orphaned_companions:
                        archive_processed_file(file_path, source_dir, archive_dir)
                else:
                    print("Leaving orphaned files in source directory.")

        # Clean up empty source directory
        if archive_dir:
            cleanup_empty_directory(source_dir)

        # Display summary
        if any(r.action in ["copied", "skipped"] for r in results):
            print("✅ Import Summary:")
            print(format_import_summary(results, archive_dir))
            print("📁 Files have been organized by date during import.")
        else:
            print("✅ No new files to copy")
    else:
        # Dry run summary
        would_copy = sum(1 for r in results if r.action == "would_copy")
        current_date = datetime.now().strftime('%Y-%m-%d')
        new_name = f"{os.path.basename(source_dir)} - copied {current_date}"

        print(f"🧪 Dry run complete. Would process {would_copy} file(s)")
        if would_copy > 0:
            print(f"   Would create archive: '{new_name}'")
            print(f"   Would remove original: '{os.path.basename(source_dir)}'")
            print("   Files would be organized into date folders")
        print()
        print("   Re-run with --apply to execute")

    return 0

if __name__ == "__main__":
    sys.exit(main())