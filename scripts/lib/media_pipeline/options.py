"""What a run was asked to do: the command line, resolved against the profile."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, replace
from typing import NoReturn, Optional

from lib import profiles, tag_media
from lib.command_line import UnknownLocation, UnknownTimezone, resolve_timezone
from lib.media_pipeline.working_dir import WORKING_DIR_NAME

# The optional steps --tasks names. Ingest, fix-timestamp (Set Timestamps) and
# output always run.
TAG = "tag"
FIX_TIMESTAMP = "fix-timestamp"
GYROFLOW = "gyroflow"
ARCHIVE_SOURCE = "archive-source"


@dataclass(frozen=True)
class RunOptions:
    """Everything a run needs to know, fixed before the first file is touched.

    Built by resolve_options() from the parsed command line and the profile it
    names; the stages and the batch read it and never change it.
    """
    source_dir: str
    target_dir: str
    working_dir: str
    extensions: list
    profile: Optional[dict] = None
    timezone: Optional[str] = None
    timezone_spec: Optional[str] = None
    tasks: frozenset = frozenset()
    group: Optional[str] = None
    apply: bool = False
    verbose: bool = False
    copy_companion_files: bool = False
    companion_extensions: Optional[list] = None
    update_filename_dates: bool = False
    infer_from_filename: bool = False
    time_offset: Optional[int] = None
    force_timezone: bool = False
    overwrite: bool = False
    allow_camera_mismatch: bool = False
    unlock_protected: bool = False
    allow_mixed_timezones: bool = False
    source_action: str = "archive"
    archive_destination: Optional[str] = None
    archived_name: Optional[str] = None
    backup_locations: tuple = ()
    gyroflow_preset: Optional[str] = None
    gyroflow_config: Optional[dict] = None

    @classmethod
    def from_args(cls, args, profile: Optional[dict], config: dict, source_dir: str,
                  target_dir: str, extensions: list,
                  timezone_spec: Optional[str]) -> RunOptions:
        """The options for parsed command-line args and the values resolved from them."""
        return cls(
            source_dir=source_dir,
            target_dir=target_dir,
            working_dir=args.working_dir or os.path.join(target_dir, WORKING_DIR_NAME),
            extensions=extensions,
            profile=profile,
            timezone=args.timezone,
            timezone_spec=timezone_spec,
            tasks=frozenset(args.tasks),
            group=args.group,
            apply=args.apply,
            verbose=args.verbose,
            copy_companion_files=args.copy_companion_files,
            companion_extensions=(profile.get("companion_extensions")
                                  if args.copy_companion_files and profile else None),
            update_filename_dates=args.update_filename_dates,
            infer_from_filename=args.infer_from_filename,
            time_offset=args.time_offset,
            force_timezone=args.force_timezone,
            overwrite=args.overwrite,
            allow_camera_mismatch=args.allow_camera_mismatch,
            unlock_protected=args.unlock_protected,
            allow_mixed_timezones=args.allow_mixed_timezones,
            source_action=args.source_action,
            archive_destination=args.archive_destination,
            archived_name=args.archived_name,
            backup_locations=tuple(args.backup_location),
            gyroflow_preset=args.gyroflow_preset,
            gyroflow_config=config.get("gyroflow"),
        )

    def runs(self, task: str) -> bool:
        """Whether --tasks asked for this optional step."""
        return task in self.tasks


def with_gyroflow_preset(opts: RunOptions) -> RunOptions:
    """opts with --gyroflow-preset merged over the configured gyroflow preset.

    Parsed only once pre-flight has passed, as it always has been, so a malformed
    preset fails the run at the same point.
    """
    if not opts.gyroflow_preset:
        return opts
    config = dict(opts.gyroflow_config or {})
    config["preset"] = json.loads(opts.gyroflow_preset)
    return replace(opts, gyroflow_config=config)


def _fail(*lines: str) -> NoReturn:
    for line in lines:
        print(line, file=sys.stderr)
    sys.exit(1)


def load_config(profile_name: str) -> tuple[dict, dict]:
    """The named profile and the whole profiles file, or exit naming what is wrong."""
    try:
        config = profiles.load_config()
        return profiles.load_profile(profile_name, config), config
    except profiles.ProfilesFileMissing as missing:
        _fail(f"ERROR: Profile file not found: {missing.path}")
    except profiles.ProfileNotFound as not_found:
        _fail(f"ERROR: Profile '{profile_name}' not found",
              f"Available profiles: {', '.join(not_found.available)}")


def apply_profile_overrides(profile: dict, args) -> None:
    """The workflow tab's ad-hoc edits: --tags, --make and --model over the profile."""
    if args.tags is not None:
        profile["tags"] = tag_media.parse_tag_list(args.tags)
    if args.make is not None:
        profile.setdefault("exif", {})["make"] = args.make
    if args.model is not None:
        profile.setdefault("exif", {})["model"] = args.model


def _profile_dir(profile: Optional[dict], key: str) -> Optional[str]:
    value = (profile or {}).get(key)
    return value if value and value != "None" else None


def directories_overlap(a: str, b: str) -> bool:
    """Whether a and b are the same directory, or one lies inside the other.

    Compared on real paths, so a symlink to a directory is that directory.
    """
    real_a, real_b = os.path.realpath(a), os.path.realpath(b)
    return os.path.commonpath([real_a, real_b]) in (real_a, real_b)


def resolve_options(args) -> RunOptions:
    """The run's options for parsed command-line arguments, or exit naming the problem."""
    profile = None
    config: dict = {}
    if args.profile:
        profile, config = load_config(args.profile)
    if profile:
        apply_profile_overrides(profile, args)

    extensions = args.extensions or (profile or {}).get("file_extensions")
    if not extensions:
        _fail("ERROR: no file types to process; declare file_extensions in the profile or pass --extensions")

    source_dir = args.source or _profile_dir(profile, "source_dir")
    target_dir = args.target or _profile_dir(profile, "ready_dir")
    if not source_dir:
        _fail("ERROR: --source is required (or use --profile with source_dir)")
    if not target_dir:
        _fail("ERROR: --target is required (or use --profile with ready_dir)")
    if not os.path.isdir(source_dir):
        _fail(f"ERROR: Source directory not found: {source_dir}")
    # The source is never modified, so a file renamed on its way out would land
    # beside its original, and archive-source would take the library for a card.
    if directories_overlap(source_dir, target_dir):
        _fail(f"ERROR: Source and target overlap: {source_dir} and {target_dir}",
              "The source is copied from, never changed, so processing a folder into "
              "itself leaves every renamed file beside its original. "
              "Choose a target outside the source.")

    try:
        timezone_spec = resolve_timezone(args.timezone, args.location)
    except UnknownTimezone:
        _fail(f"ERROR: unknown timezone '{args.timezone}' — use an IANA zone name (e.g., Pacific/Auckland) or a +HHMM offset")
    except UnknownLocation:
        _fail(f"ERROR: Could not determine timezone for location '{args.location}'")

    # Every run sets timestamps, and the date folder is the date where the footage
    # was shot: neither has an answer without the zone it was shot in.
    if not timezone_spec:
        _fail("ERROR: --timezone (or --location) is required: it says where the footage was shot")
    if args.infer_from_filename and not args.timezone:
        _fail("ERROR: --infer-from-filename requires --timezone")

    return RunOptions.from_args(args, profile, config, source_dir, target_dir,
                                extensions, timezone_spec)
