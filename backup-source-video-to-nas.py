#!/usr/bin/env python3
"""
Backup source video to NAS using profile-based configuration
Generates exclusion patterns from media profiles and calls backup-to-nas.sh
"""

import subprocess
import sys
import os
import argparse

# Ensure we're running with the media-import venv
try:
    import yaml
except ImportError:
    # Try to find and use the venv
    script_dir = os.path.dirname(os.path.abspath(__file__))
    venv_python = os.path.join(script_dir, 'media-import', 'bin', 'python3')
    if os.path.exists(venv_python):
        # Re-exec with venv python
        os.execv(venv_python, [venv_python] + sys.argv)
    else:
        print("Error: yaml module not found and venv not available", file=sys.stderr)
        print(f"Expected venv at: {venv_python}", file=sys.stderr)
        sys.exit(1)

import signal
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Handle Ctrl-C gracefully
def signal_handler(sig, frame):  # noqa: ARG001 (unused but required by signal.signal)
    print("\n\nInterrupted by user", file=sys.stderr)
    sys.exit(130)

signal.signal(signal.SIGINT, signal_handler)

def load_config(profile_path: str) -> Tuple[Dict, Dict]:
    """Load media profiles and backup config from YAML file

    Returns: (profiles, backup_config)
    """
    try:
        with open(profile_path, 'r') as f:
            data = yaml.safe_load(f)
        return data.get('profiles', {}), data.get('backup_config', {})
    except Exception as e:
        print(f"Error loading config from {profile_path}: {e}", file=sys.stderr)
        return {}, {}

def get_default_profile_path() -> str:
    """Get default profile file path"""
    script_dir = Path(__file__).parent
    for filename in ['media-profiles.yaml', 'media-profiles.yml']:
        profile_path = script_dir / filename
        if profile_path.exists():
            return str(profile_path)
    return str(script_dir / 'media-profiles.yaml')

def transform_local_to_remote_path(local_path: str, local_base_path: str, remote_base_path: str) -> str:
    """Transform a local path to its corresponding remote path

    Example: /Volumes/Extreme GRN/Videos -> /volume1/Backup/ChronoSync/Extreme GRN/Videos
    """
    if not local_path.startswith(local_base_path):
        raise ValueError(f"Local path '{local_path}' does not start with local_base_path '{local_base_path}'")

    relative_path = local_path[len(local_base_path):]
    return os.path.join(remote_base_path, relative_path)

def main():
    """Main entry point"""
    # Parse arguments (only --profile, pass through everything else)
    parser = argparse.ArgumentParser(
        description='Backup source video to NAS using media profiles',
        add_help=False  # Don't interfere with backup-to-nas.sh --help
    )
    parser.add_argument('--profile', type=str, help='Only backup this specific profile')
    args, remaining_args = parser.parse_known_args()

    # Load profiles and backup config
    profiles_file = get_default_profile_path()
    profiles, backup_config = load_config(profiles_file)

    if not profiles:
        print("Error: No profiles found", file=sys.stderr)
        return 1

    # Get required config
    local_base_path = backup_config.get('local_base_path')
    remote_base_path = backup_config.get('remote_base_path')

    if not local_base_path:
        print("Error: local_base_path not found in backup_config", file=sys.stderr)
        print("Add to media-profiles.yaml:", file=sys.stderr)
        print("  backup_config:", file=sys.stderr)
        print("    local_base_path: \"/Volumes/\"", file=sys.stderr)
        return 1

    if not remote_base_path:
        print("Error: remote_base_path not found in backup_config", file=sys.stderr)
        print("Add to media-profiles.yaml:", file=sys.stderr)
        print("  backup_config:", file=sys.stderr)
        print("    remote_base_path: \"/volume1/Backup/ChronoSync/\"", file=sys.stderr)
        return 1

    # Get script directory and backup-to-nas.sh path
    script_dir = Path(__file__).parent
    backup_script = script_dir / 'backup-to-nas.sh'

    if not backup_script.exists():
        print(f"Error: backup-to-nas.sh not found at {backup_script}", file=sys.stderr)
        return 1

    # Collect enabled profiles
    enabled_profiles = []
    for profile_name, profile_config in profiles.items():
        if not profile_config.get('backup_enabled', False):
            continue
        backup_dir = profile_config.get('backup_dir')
        if not backup_dir:
            continue
        enabled_profiles.append((profile_name, profile_config))

    if not enabled_profiles:
        print("Error: No backup_dir specified in any enabled profile", file=sys.stderr)
        print("Set backup_enabled: true for at least one profile in media-profiles.yaml", file=sys.stderr)
        return 1

    # Filter by --profile if specified
    if args.profile:
        filtered = [(name, config) for name, config in enabled_profiles if name == args.profile]
        if not filtered:
            # Check if profile exists but isn't enabled
            if args.profile in profiles:
                print(f"Error: Profile '{args.profile}' exists but backup_enabled is not true", file=sys.stderr)
            else:
                print(f"Error: Profile '{args.profile}' not found in media-profiles.yaml", file=sys.stderr)
                print(f"Available profiles: {', '.join(profiles.keys())}", file=sys.stderr)
            return 1
        enabled_profiles = filtered
        print(f"Backing up profile: {args.profile}")
    else:
        print(f"Found {len(enabled_profiles)} profile(s) with backup enabled")
    print()

    # Run backup for each enabled profile
    for profile_name, profile_config in enabled_profiles:
        backup_dir = profile_config['backup_dir']
        backup_exclude_subdirs = profile_config.get('backup_exclude_subdirs', [])

        # Transform local path to remote path
        try:
            remote_path = transform_local_to_remote_path(backup_dir, local_base_path, remote_base_path)
        except ValueError as e:
            print(f"Error for profile '{profile_name}': {e}", file=sys.stderr)
            return 1

        # Ensure both source and dest have trailing slashes for rsync
        source_path = backup_dir.rstrip('/') + '/'
        dest_path = remote_path.rstrip('/') + '/'

        # Display what we're doing
        print(f"=== Backing up profile: {profile_name} ===")
        print(f"Source: {source_path}")
        print(f"Destination: {dest_path}")
        if backup_exclude_subdirs:
            print(f"Excluding subdirs: {', '.join(backup_exclude_subdirs)}")
        print()

        # Build command for backup-to-nas.sh
        cmd = [
            str(backup_script),
            '--source', source_path,
            '--dest', dest_path
        ]

        # Add exclusions if specified
        if backup_exclude_subdirs:
            # Join with pipe separator as expected by backup-to-nas.sh
            exclude_pattern = '|'.join(f"{subdir}/" for subdir in backup_exclude_subdirs)
            cmd.extend(['--exclude', exclude_pattern])

        # Pass through remaining command-line arguments (excluding --profile)
        cmd.extend(remaining_args)

        # Execute backup-to-nas.sh
        try:
            result = subprocess.run(cmd)
            if result.returncode != 0:
                print(f"\nWarning: Backup for profile '{profile_name}' failed with code {result.returncode}", file=sys.stderr)
                return result.returncode
        except KeyboardInterrupt:
            return 130
        except Exception as e:
            print(f"Error executing backup for profile '{profile_name}': {e}", file=sys.stderr)
            return 1

        print()

    print("✅ All profile backups completed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
