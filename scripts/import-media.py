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

sys.path.insert(0, str(Path(__file__).parent))
from lib.filesystem import cleanup_empty_parent_dirs, parse_machine_output

# Handle Ctrl-C gracefully
def signal_handler(sig, frame):
    print("\n\nInterrupted by user", file=sys.stderr)
    sys.exit(130)

signal.signal(signal.SIGINT, signal_handler)

class ImportProfile(NamedTuple):
    """Configuration profile for media import"""
    import_dir: str
    source_dir: Optional[str] = None
    file_extensions: Optional[List[str]] = None
    companion_extensions: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    exif_make: Optional[str] = None
    exif_model: Optional[str] = None

class ImportResult(NamedTuple):
    """Result of importing a single file"""
    success: bool
    source_path: str
    action: str = ""  # copied, moved, skipped, overwrote
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
                source_dir=config.get('source_dir'),
                file_extensions=config.get('file_extensions'),
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

def organize_file(file_path: str, import_dir: str, group: str, copy_mode: bool = True, apply_changes: bool = False) -> ImportResult:
    """Organize a single file using organize-by-date.sh

    organize-by-date.sh outputs:
    - stderr: human-readable messages (passed through to user)
    - stdout: machine-readable data prefixed with @@ (e.g., @@dest=/path/to/file)

    We need the dest path because tagging happens AFTER copy - tagging the destination
    is much faster than tagging on a slow memory card.
    """
    script_dir = Path(__file__).parent
    organize_script = script_dir / 'organize-by-date.sh'

    template = f'{{{{YYYY}}}}/{group}/{{{{YYYY}}}}-{{{{MM}}}}-{{{{DD}}}}'
    cmd = [str(organize_script), file_path, '--target', import_dir, '--template', template]
    if copy_mode:
        cmd.append('--copy')
    if apply_changes:
        cmd.append('--apply')

    try:
        # Capture stdout (machine data), let stderr pass through to user
        result = subprocess.run(cmd, text=True, check=True, stdout=subprocess.PIPE)

        data = parse_machine_output(result.stdout)
        dest_path = data.get('dest')
        action = data.get('action', '')

        return ImportResult(True, file_path, action=action, dest_path=dest_path)

    except subprocess.CalledProcessError:
        # stderr already passed through to user
        return ImportResult(False, file_path, action='failed')

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

def get_media_files(directory: str, include_companion: bool = True, companion_extensions: Optional[List[str]] = None, file_extensions: Optional[List[str]] = None) -> List[str]:
    """Get all media files from directory, excluding system files

    Args:
        directory: Directory to search
        include_companion: If True, include companion files
        companion_extensions: List of companion file extensions (e.g., ['.lrv', '.thm'])
        file_extensions: List of allowed file extensions (e.g., ['.mp4', '.mov']). If None, all files are included.

    Returns:
        List of file paths matching the criteria
    """
    media_files = []

    # Default companion extensions (GoPro and DJI)
    if companion_extensions is None:
        companion_extensions = ['.lrv', '.thm', '.lrf']

    # Convert to lowercase sets for case-insensitive lookup
    companion_exts = {ext.lower() for ext in companion_extensions}
    allowed_exts = {ext.lower() for ext in file_extensions} if file_extensions else None

    for root, _, files in os.walk(directory):
        for file in files:
            if file.startswith('.') or file in ['.DS_Store', 'Thumbs.db']:
                continue

            file_ext = Path(file).suffix.lower()

            # Skip companion files if not wanted
            if not include_companion and file_ext in companion_exts:
                continue

            # If file_extensions specified, only include matching files (and companion files if wanted)
            if allowed_exts is not None:
                is_allowed = file_ext in allowed_exts
                is_companion = file_ext in companion_exts

                # Include if it's an allowed extension, or if it's a companion and we want companions
                if not (is_allowed or (is_companion and include_companion)):
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
    """Create archive directory as sibling to source_dir in pwd"""
    if not apply_changes:
        return None

    current_date = datetime.now().strftime('%Y-%m-%d')
    archive_name = f"{os.path.basename(original_dir)} - copied {current_date}"
    archive_path = os.path.join(os.path.dirname(original_dir) or ".", archive_name)

    os.makedirs(archive_path, exist_ok=True)
    return archive_path

def is_file_locked(file_path: str) -> bool:
    """Check if file has macOS locked (uchg) flag"""
    try:
        import stat
        flags = os.stat(file_path).st_flags
        return bool(flags & stat.UF_IMMUTABLE)
    except (OSError, AttributeError):
        return False

def archive_processed_file(file_path: str, source_dir: str, archive_dir: Optional[str]) -> bool:
    """Move processed file to archive directory, preserving relative directory structure"""
    if not archive_dir:
        return True

    # Check for locked source file (macOS) - can't delete after copying
    if is_file_locked(file_path):
        print(f"⚠️  Skipped archive (source file locked): {os.path.relpath(file_path, source_dir)}", file=sys.stderr)
        return True  # Not a failure, just can't archive

    # Save the directory before moving the file
    source_file_dir = os.path.dirname(file_path)

    # Preserve directory structure relative to source_dir
    rel_path = os.path.relpath(file_path, source_dir)
    archive_file_path = os.path.join(archive_dir, rel_path)

    # Check if destination already exists and is locked (from previous failed run)
    if os.path.exists(archive_file_path) and is_file_locked(archive_file_path):
        print(f"⚠️  Skipped archive (dest file locked): {os.path.relpath(file_path, source_dir)}", file=sys.stderr)
        return True

    # Create parent directories if needed
    os.makedirs(os.path.dirname(archive_file_path), exist_ok=True)

    try:
        # Try move first (fastest for same filesystem)
        shutil.move(file_path, archive_file_path)

        # Clean up empty parent directories after moving
        cleanup_empty_parent_dirs(source_file_dir, source_dir)

        return True

    except (OSError, PermissionError):
        # Move failed - try cp command fallback (handles macOS extended attributes better)
        try:
            result = subprocess.run(['cp', '-p', file_path, archive_file_path], capture_output=True, text=True)
            if result.returncode != 0:
                raise OSError(result.stderr.strip() or f"cp failed with code {result.returncode}")

            # Try to delete source
            try:
                os.remove(file_path)
                # Clean up empty parent directories after successful delete
                cleanup_empty_parent_dirs(source_file_dir, source_dir)
                return True
            except (OSError, PermissionError):
                # Copy succeeded but delete failed - could be locked file or read-only media
                if is_file_locked(file_path):
                    print(f"⚠️  Copied to archive but source locked (delete manually): {os.path.relpath(file_path, source_dir)}", file=sys.stderr)
                else:
                    print(f"   Note: Archived {os.path.relpath(file_path, source_dir)} (source retained on read-only media)", file=sys.stderr)
                return True

        except Exception as copy_error:
            abs_archive = os.path.abspath(archive_file_path)
            print(f"Warning: Failed to archive {os.path.relpath(file_path, source_dir)} → {abs_archive}: {copy_error}", file=sys.stderr)
            return False

def format_import_summary(results: List[ImportResult], archive_dir: Optional[str]) -> str:
    """Format import summary from results"""
    succeeded = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)

    lines = []
    if succeeded > 0:
        lines.append(f"   - Processed: {succeeded} file(s)")
    if failed > 0:
        lines.append(f"   - Failed: {failed} file(s)")
    if archive_dir:
        lines.append(f"   - Archived to: {os.path.basename(archive_dir)}")

    return '\n'.join(lines)

def import_media(source_dir: str, profile: ImportProfile, group: str,
                 apply_changes: bool = False, skip_companion: bool = False) -> tuple[List[ImportResult], Optional[str], List[str]]:
    """Main import function - processes all files in source directory

    Returns: (results, archive_dir, companion_files_to_archive)
    """

    # Get files to import (may exclude companions)
    import_files = get_media_files(
        source_dir,
        include_companion=not skip_companion,
        companion_extensions=profile.companion_extensions,
        file_extensions=profile.file_extensions
    )

    # Get ALL files for archiving (capture this BEFORE we start moving files)
    all_files = get_media_files(
        source_dir,
        include_companion=True,
        companion_extensions=profile.companion_extensions,
        file_extensions=profile.file_extensions
    )

    # Calculate which files won't be imported but need archiving
    import_files_set = set(import_files)
    companion_files_to_archive = [f for f in all_files if f not in import_files_set]

    if not import_files and not companion_files_to_archive:
        print("No media files found to process", file=sys.stderr)
        return [], None, []

    if not import_files:
        print(f"No media files to import ({len(companion_files_to_archive)} companion file(s) to archive)", file=sys.stderr)
        return [], None, companion_files_to_archive

    if skip_companion:
        companion_count = len(companion_files_to_archive)
        print(f"Found {len(import_files)} file(s) to import ({companion_count} companion files will be archived only)", file=sys.stderr)
    else:
        print(f"Found {len(import_files)} file(s) to process", file=sys.stderr)
    print(file=sys.stderr)

    # Process files for import
    results = []
    archive_dir = None

    for i, file_path in enumerate(import_files, 1):
        filename = os.path.basename(file_path)

        if apply_changes:
            print(f"[{i}/{len(import_files)}] Processing: {filename}", file=sys.stderr)

        # Organize the file (copy to destination)
        result = organize_file(file_path, profile.import_dir, group, copy_mode=True, apply_changes=apply_changes)
        results.append(result)

        if not result.success:
            # Error already displayed by organize-by-date.sh
            continue

        # Tag the DESTINATION file only if it was actually copied/moved (not skipped)
        # Skipped files already exist at destination and were presumably already tagged
        if apply_changes and result.action in ('copied', 'moved', 'overwrote') and result.dest_path and os.path.exists(result.dest_path):
            if not tag_file(result.dest_path, tags=profile.tags, make=profile.exif_make, model=profile.exif_model, apply_changes=apply_changes):
                print(f"   Warning: Tagging failed for {filename}", file=sys.stderr)

        # For successfully processed files in apply mode, archive the source file immediately
        # This ensures progress is preserved in case of interruption
        # Only archive if source file still exists (skipped files in copy mode still exist)
        if apply_changes and result.success and os.path.exists(file_path):
            # Create archive directory on first successful file
            if not archive_dir:
                archive_dir = create_archive_directory(source_dir, apply_changes)
                if archive_dir:
                    print(f"Created archive folder: {os.path.basename(archive_dir)}", file=sys.stderr)

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
  %(prog)s --profile insta360 --group Japan --apply
  %(prog)s --profile gopro --group Japan DCIM --apply
  %(prog)s --profile gopro --group Japan DCIM --skip-companion --apply
        """
    )

    parser.add_argument('source_dir', nargs='?',
                       help='Source directory (auto-detected if only one subdirectory exists)')
    parser.add_argument('--profile',
                       help='Profile name from configuration file')
    parser.add_argument('--group',
                       help='Group name for organizing dates (e.g., "Japan", "Wedding")')
    parser.add_argument('--skip-companion', action='store_true',
                       help='Skip companion files (.lrv, .thm) - saves space, recommended for video editor workflows')
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
            print("Available profiles:", file=sys.stderr)
            for name, profile in profiles.items():
                print(f"  {name:12} → {profile.import_dir}", file=sys.stderr)
        else:
            print("No profiles found", file=sys.stderr)
            print(f"Create a profiles file at: {profiles_file}", file=sys.stderr)
        return 0

    # Validate required arguments
    if not args.profile:
        print("Error: --profile is required", file=sys.stderr)
        print("Use --list-profiles to see available profiles", file=sys.stderr)
        return 1

    if not args.group:
        print("Error: --group is required", file=sys.stderr)
        return 1

    # Load profile
    if args.profile not in profiles:
        print(f"Error: Profile '{args.profile}' not found", file=sys.stderr)
        print(f"Available profiles: {', '.join(profiles.keys())}", file=sys.stderr)
        return 1

    profile = profiles[args.profile]

    # Find source directory (profile's source_dir used as default)
    specified_dir = args.source_dir or profile.source_dir
    try:
        source_dir = find_source_directory(specified_dir)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Require subdirectory, not "."
    if source_dir == ".":
        print("Error: Must specify a subdirectory (e.g., DCIM), not '.'", file=sys.stderr)
        return 1

    # Check if already processed
    if '- copied' in os.path.basename(source_dir):
        response = input(f"Directory '{os.path.basename(source_dir)}' appears already processed. Continue? (y/N) ")
        if not response.lower().startswith('y'):
            return 0

    # Display configuration
    print(f"→ Source:      {source_dir}", file=sys.stderr)
    print(f"→ Import target: {profile.import_dir}", file=sys.stderr)
    print(f"→ Mode:        {'APPLY' if args.apply else 'DRY RUN (no changes)'}", file=sys.stderr)
    print(file=sys.stderr)

    # Import media
    results, archive_dir, companion_files = import_media(
        source_dir, profile, args.group,
        apply_changes=args.apply,
        skip_companion=args.skip_companion
    )

    if not results and not companion_files:
        return 0

    print(file=sys.stderr)

    # Handle post-processing for apply mode
    if args.apply:
        # Check for companion files that need archiving
        orphaned_companions = []
        for file_path in companion_files:
            if os.path.exists(file_path):
                orphaned_companions.append(file_path)

        if orphaned_companions:
            print(f"\n⚠️  Found {len(orphaned_companions)} companion file(s) to archive:", file=sys.stderr)
            for orphan in orphaned_companions:
                print(f"   - {os.path.basename(orphan)}", file=sys.stderr)

            response = input("\nArchive these files? (y/N) ")
            if response.lower().startswith('y'):
                # Create archive directory if needed
                if not archive_dir:
                    archive_dir = create_archive_directory(source_dir, args.apply)
                if archive_dir:
                    for file_path in orphaned_companions:
                        archive_processed_file(file_path, source_dir, archive_dir)
                    print(f"Archived to: {os.path.basename(archive_dir)}", file=sys.stderr)
            else:
                print("Leaving companion files in source directory.", file=sys.stderr)

        # Display summary
        print("✅ Import complete", file=sys.stderr)
        print(format_import_summary(results, archive_dir), file=sys.stderr)
    else:
        # Dry run summary
        would_process = sum(1 for r in results if r.success)
        current_date = datetime.now().strftime('%Y-%m-%d')
        new_name = f"{os.path.basename(source_dir)} - copied {current_date}"

        print(f"🧪 Dry run complete. Would process {would_process} file(s)", file=sys.stderr)
        if would_process > 0:
            print(f"   Would archive source files to: '{new_name}'", file=sys.stderr)
            print("   Files would be organized into date folders", file=sys.stderr)
        if companion_files:
            print(f"   Would prompt to archive {len(companion_files)} companion file(s)", file=sys.stderr)
        print(file=sys.stderr)
        print("   Re-run with --apply to execute", file=sys.stderr)

    return 0

if __name__ == "__main__":
    sys.exit(main())