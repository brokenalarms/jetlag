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

def format_bytes(num_bytes: float) -> str:
    """Format bytes as human-readable string"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(num_bytes) < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} PB"


def parse_rsync_output(stdout: str) -> dict:
    """Parse @@key=value lines from rsync output"""
    stats = {
        'files_transferred': 0,
        'bytes_transferred': 0,
        'total_size': 0,
        'elapsed_seconds': 0
    }
    for line in stdout.split('\n'):
        if line.startswith('@@'):
            key_value = line[2:]  # Remove @@
            if '=' in key_value:
                key, value = key_value.split('=', 1)
                if key in stats:
                    try:
                        stats[key] = int(value)
                    except ValueError:
                        pass
    return stats


def format_speed(bytes_per_sec: float) -> str:
    """Format speed as human-readable string"""
    if bytes_per_sec >= 1024 * 1024:
        return f"{bytes_per_sec / (1024 * 1024):.2f} MB/s"
    elif bytes_per_sec >= 1024:
        return f"{bytes_per_sec / 1024:.2f} KB/s"
    else:
        return f"{bytes_per_sec:.0f} B/s"


def print_summary(profile_stats: list, total_stats: dict, interrupted: bool = False):
    """Print backup summary"""
    print("=" * 50, file=sys.stderr)
    if interrupted:
        print("📊 BACKUP SUMMARY (interrupted)", file=sys.stderr)
    else:
        print("📊 BACKUP SUMMARY", file=sys.stderr)
    print("-" * 50, file=sys.stderr)

    for ps in profile_stats:
        status = "✅" if ps['success'] else "❌"
        files = ps['stats']['files_transferred']
        bytes_str = format_bytes(ps['stats']['bytes_transferred'])
        print(f"{status} {ps['name']}: {files} files, {bytes_str}", file=sys.stderr)

    print("-" * 50, file=sys.stderr)
    print(f"Total profiles: {total_stats['profiles_completed']} succeeded, {total_stats['profiles_failed']} failed", file=sys.stderr)
    print(f"Total files transferred: {total_stats['files_transferred']}", file=sys.stderr)
    print(f"Total data transferred: {format_bytes(total_stats['bytes_transferred'])}", file=sys.stderr)

    # Calculate and display average speed
    elapsed = total_stats.get('elapsed_seconds', 0)
    if elapsed > 0 and total_stats['bytes_transferred'] > 0:
        avg_speed = total_stats['bytes_transferred'] / elapsed
        print(f"Average speed: {format_speed(avg_speed)} ({elapsed}s)", file=sys.stderr)

    print("=" * 50, file=sys.stderr)


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
        print(f"Backing up profile: {args.profile}", file=sys.stderr)
    else:
        print(f"Found {len(enabled_profiles)} profile(s) with backup enabled", file=sys.stderr)
    print(file=sys.stderr)

    # Track aggregate stats
    total_stats = {
        'files_transferred': 0,
        'bytes_transferred': 0,
        'total_size': 0,
        'elapsed_seconds': 0,
        'profiles_completed': 0,
        'profiles_failed': 0
    }
    profile_stats = []
    interrupted = False

    # Set up SIGINT handler - just set flag, let current subprocess finish
    def sigint_handler(sig, frame):
        nonlocal interrupted
        interrupted = True
        print("\n\nInterrupted by user - waiting for current transfer to report stats...", file=sys.stderr)

    signal.signal(signal.SIGINT, sigint_handler)

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
        print(f"=== Backing up profile: {profile_name} ===", file=sys.stderr)
        print(f"Source: {source_path}", file=sys.stderr)
        print(f"Destination: {dest_path}", file=sys.stderr)
        if backup_exclude_subdirs:
            print(f"Excluding subdirs: {', '.join(backup_exclude_subdirs)}", file=sys.stderr)
        print(file=sys.stderr)

        # Build command for backup-to-nas.sh
        # Pass --machine-readable to get @@ stats on stdout for parsing
        cmd = [
            str(backup_script),
            '--source', source_path,
            '--dest', dest_path,
            '--machine-readable'
        ]

        # Add exclusions if specified
        if backup_exclude_subdirs:
            # Join with pipe separator as expected by backup-to-nas.sh
            exclude_pattern = '|'.join(f"{subdir}/" for subdir in backup_exclude_subdirs)
            cmd.extend(['--exclude', exclude_pattern])

        # Pass through remaining command-line arguments (excluding --profile)
        cmd.extend(remaining_args)

        # Execute backup-to-nas.sh
        # Let stderr pass through in real-time, only capture stdout for @@ lines
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=None, text=True)
        except Exception as e:
            print(f"Error executing backup for profile '{profile_name}': {e}", file=sys.stderr)
            total_stats['profiles_failed'] += 1
            continue

        # Parse stats from stdout
        stats = parse_rsync_output(result.stdout)

        # Profile is successful only if returncode is 0 AND not interrupted
        profile_success = result.returncode == 0 and not interrupted
        profile_stats.append({
            'name': profile_name,
            'stats': stats,
            'success': profile_success
        })

        if not profile_success:
            if interrupted:
                print(f"\nProfile '{profile_name}' interrupted", file=sys.stderr)
            else:
                print(f"\nWarning: Backup for profile '{profile_name}' failed with code {result.returncode}", file=sys.stderr)
            total_stats['profiles_failed'] += 1
        else:
            total_stats['profiles_completed'] += 1

        # Always add stats (even from interrupted/failed transfers)
        total_stats['files_transferred'] += stats['files_transferred']
        total_stats['bytes_transferred'] += stats['bytes_transferred']
        total_stats['total_size'] += stats['total_size']
        total_stats['elapsed_seconds'] += stats['elapsed_seconds']

        print(file=sys.stderr)

        # If interrupted, stop after this profile
        if interrupted:
            break

    # Print summary
    print_summary(profile_stats, total_stats, interrupted=interrupted)

    if interrupted:
        return 130

    if total_stats['profiles_failed'] > 0:
        return 1

    print("✅ All profile backups completed", file=sys.stderr)
    return 0

if __name__ == "__main__":
    sys.exit(main())
