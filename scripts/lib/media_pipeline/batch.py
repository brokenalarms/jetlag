"""A whole run: options, pre-flight, every file, then the batch-level steps."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import NoReturn

from lib import archive_source
from lib.verify_card import cleared_files, verify_card
from lib.filesystem import find_media_files
from lib.media_pipeline.events import emit_event
from lib.media_pipeline.options import ARCHIVE_SOURCE, RunOptions, resolve_options, with_gyroflow_preset
from lib.media_pipeline.preflight import (
    DESTINATION_OCCUPIED, Finding, check_stale_exiftool_tmp, report_finding, run_checks,
)
from lib.media_pipeline.stages import process_file
from lib.media_pipeline.working_dir import WorkingDir


@dataclass
class BatchStats:
    """The run's counts, and what its batch-level steps need from the files."""
    processed: int = 0
    succeeded: int = 0
    changed: int = 0
    failed_files: list[str] = field(default_factory=list)
    unprocessed_files: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    organize_conflicts: list[str] = field(default_factory=list)

    @property
    def failed(self) -> int:
        return len(self.failed_files)


def print_configuration(opts: RunOptions) -> None:
    print(f"→ Source:  {opts.source_dir}", file=sys.stderr)
    print(f"→ Target:  {opts.target_dir}", file=sys.stderr)
    print(f"→ Mode:    {'APPLY (files will be processed)' if opts.apply else 'DRY RUN (no changes)'}", file=sys.stderr)
    if opts.timezone_spec:
        print(f"→ Timezone: {opts.timezone_spec}", file=sys.stderr)
    else:
        print("→ Timezone: From video metadata (or will prompt if needed)", file=sys.stderr)
    if opts.runs(ARCHIVE_SOURCE):
        print(f"→ Source action: {opts.source_action}", file=sys.stderr)
    print(f"→ Copy companions: {'yes' if opts.copy_companion_files else 'no'}", file=sys.stderr)
    print(file=sys.stderr)


def discover_files(opts: RunOptions) -> list[Path]:
    """The source's media files, in processing order; exits 0 when there are none."""
    files = find_media_files(opts.source_dir, opts.extensions)
    if not files:
        emit_event("no_media_files", source=opts.source_dir, extensions=list(opts.extensions))
        print(f"No {', '.join(opts.extensions)} files found in {opts.source_dir}", file=sys.stderr)
        sys.exit(0)
    print(f"Found {len(files)} {', '.join(opts.extensions)} file(s) to process", file=sys.stderr)
    print(file=sys.stderr)
    return files


def process_files(files: list[Path], opts: RunOptions, working_dir: WorkingDir) -> BatchStats:
    """Every file through its stages, one at a time, so an interrupted run
    resumes from the next unprocessed file.

    An apply stops once its working directory is gone: the destination volume
    disconnected, and every file after it would fail the same way.
    """
    stats = BatchStats()
    for i, file_path in enumerate(files, 1):
        if opts.apply and not working_dir.exists():
            stats.unprocessed_files = [f.name for f in files[i - 1:]]
            print(f"❌ The destination is gone ({opts.target_dir}): was the drive disconnected? "
                  f"Stopping with {len(stats.unprocessed_files)} file(s) not processed.",
                  file=sys.stderr)
            break
        stats.processed += 1
        print(f"[{i}/{len(files)}] Processing: {file_path.name}", file=sys.stderr)

        result = process_file(file_path, opts, working_dir)
        if result.failed:
            stats.failed_files.append(file_path.name)
        else:
            stats.succeeded += 1
            if result.changed:
                stats.changed += 1
        stats.source_files.extend(result.source_files)
        if result.organize_conflict:
            stats.organize_conflicts.append(result.organize_conflict)

        print(file=sys.stderr)  # Empty line between files
    return stats


def report_organize_conflicts(stats: BatchStats, opts: RunOptions) -> None:
    """One batch-level finding of what --overwrite would unblock, so the app has a
    single thing to ask about instead of re-deriving it from the per-file rows."""
    if stats.organize_conflicts:
        report_finding(DESTINATION_OCCUPIED, Finding(stats.organize_conflicts), opts)


def act_on_source(opts: RunOptions, stats: BatchStats) -> bool:
    """Archive or delete the source once every file is through; True when that
    was attempted and failed.

    A failed file's only copy may still be in the source directory, so archiving
    it away after failures would strand it.
    """
    if not opts.runs(ARCHIVE_SOURCE):
        return False
    if stats.failed > 0:
        print(f"📦 Skipping archive source: {stats.failed} file(s) failed.", file=sys.stderr)
        return False
    if stats.unprocessed_files:
        print(f"📦 Skipping archive source: {len(stats.unprocessed_files)} file(s) not processed.",
              file=sys.stderr)
        return False
    print("📦 Archive source...", file=sys.stderr)
    if opts.source_action == "delete":
        arc_result = archive_source.delete_files(opts.source_dir, stats.source_files, opts.apply,
                                                 verified_on_backups(opts))
    else:
        arc_result = archive_source.archive_source(
            opts.source_dir, opts.apply,
            destination=opts.archive_destination,
            archived_name=opts.archived_name,
        )
    if arc_result.failed:
        print("   ⚠️  Archive-source failed", file=sys.stderr)
    return arc_result.failed


def verified_on_backups(opts: RunOptions) -> set[Path]:
    """The source files verify-card matches on every --backup-location.

    Delete removes nothing else: a file not provably backed up keeps its last copy.
    """
    if not opts.backup_locations:
        print("   Delete needs --backup-location to verify the source against; "
              "nothing is deleted without it.", file=sys.stderr)
        return set()
    companions = list(opts.companion_extensions or [])
    report = verify_card(Path(opts.source_dir), list(opts.backup_locations), list(opts.extensions),
                         companions, opts.copy_companion_files, [])
    return cleared_files(report, Path(opts.source_dir))


def finish_working_dir(opts: RunOptions, stats: BatchStats) -> None:
    """Remove the working dir after a clean apply; keep it after a failure."""
    if not opts.apply:
        return
    if stats.failed > 0:
        print(f"⚠️  Working dir preserved for inspection: {opts.working_dir}", file=sys.stderr)
        return
    try:
        os.rmdir(opts.working_dir)
    except OSError:
        leftovers = len(os.listdir(opts.working_dir)) if os.path.isdir(opts.working_dir) else 0
        if leftovers:
            print(f"⚠️  {leftovers} file(s) left in the working dir after a run "
                  "with no failures", file=sys.stderr)


def print_summary(stats: BatchStats, apply: bool, source_action_failed: bool) -> None:
    """Print pipeline summary to stderr."""
    print(file=sys.stderr)
    print("===========================================", file=sys.stderr)
    print("📊 MEDIA PIPELINE SUMMARY", file=sys.stderr)
    print("-------------------------------------------", file=sys.stderr)
    print(f"Total files processed: {stats.processed}", file=sys.stderr)
    print(f"Successfully completed: {stats.succeeded}", file=sys.stderr)
    print(f"Files changed: {stats.changed}", file=sys.stderr)
    print(f"Files unchanged: {stats.succeeded - stats.changed}", file=sys.stderr)

    if stats.failed > 0:
        print(f"Failed: {stats.failed}", file=sys.stderr)
        print(file=sys.stderr)
        print("Failed files:", file=sys.stderr)
        for f in stats.failed_files:
            print(f"  - {f}", file=sys.stderr)

    if stats.unprocessed_files:
        print(f"Not processed, the destination is gone: {len(stats.unprocessed_files)}",
              file=sys.stderr)

    if source_action_failed:
        print("❌ Archive source failed: see the archive-source lines above.", file=sys.stderr)

    if stats.unprocessed_files:
        print("❌ Media pipeline stopped - the destination disconnected. Reconnect it and run again.",
              file=sys.stderr)
    elif apply and stats.failed > 0:
        print(f"❌ Media pipeline complete - {stats.failed} file(s) failed and were left in the working directory.", file=sys.stderr)
    elif apply:
        print("✅ Media pipeline complete - changes applied.", file=sys.stderr)
    else:
        print("✅ Media pipeline complete - DRY RUN.", file=sys.stderr)
        print("   Use --apply to execute timestamp fixes and file organization.", file=sys.stderr)


def report_summary(stats: BatchStats, apply: bool, source_action_failed: bool) -> None:
    """The run's outcome as data, for the app's completion popup, and as text for
    the log. Neither side reads the other."""
    emit_event("pipeline_summary",
        processed=stats.processed,
        succeeded=stats.succeeded,
        changed=stats.changed,
        failed=stats.failed,
        failed_files=stats.failed_files,
        unprocessed_files=stats.unprocessed_files,
        source_action_failed=source_action_failed,
        mode="applied" if apply else "dry_run",
    )
    print_summary(stats, apply, source_action_failed)


def run(args, working_dir: WorkingDir) -> NoReturn:
    """Run the pipeline for parsed command-line arguments; always exits.

    working_dir is the WorkingDir the cancel handler closes over; an apply
    creates it.
    """
    opts = resolve_options(args)
    check_stale_exiftool_tmp(opts.source_dir)

    working_dir.path = opts.working_dir
    if opts.apply:
        working_dir.create()

    print_configuration(opts)
    files = discover_files(opts)
    run_checks(files, opts)

    stats = process_files(files, with_gyroflow_preset(opts), working_dir)
    report_organize_conflicts(stats, opts)
    source_action_failed = act_on_source(opts, stats)
    finish_working_dir(opts, stats)
    report_summary(stats, opts.apply, source_action_failed)
    sys.exit(1 if stats.failed > 0 or stats.unprocessed_files or source_action_failed else 0)
