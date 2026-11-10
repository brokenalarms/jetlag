"""One file's trip through the pipeline, as a list of stages run by one loop.

INGEST (always) → [tag] → [fix-timestamp | provenance] → OUTPUT (always) → [gyroflow]

Each stage says whether the run's options enable it and does its work on the
file's FileContext, returning a StageOutcome. process_file() owns everything
around that: the stage_complete events, and the single exit a failed stage
takes. Adding a step means one Stage subclass plus its schema entry.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from lib import fix_media_timestamp, generate_gyroflow, ingest_media, organize_by_date, tag_media
from lib.exiftool import MetadataWriteRefused, exiftool
from lib.media_pipeline.events import emit_event
from lib.media_pipeline.options import FIX_TIMESTAMP, GYROFLOW, TAG, RunOptions
from lib.media_pipeline.working_dir import WorkingDir
from lib.timestamps.provenance import provenance_field_args
from lib.timestamps.sources import build_filename, carry_exif_cache, parse_datetime_original, read_exif_data


@dataclass
class FileContext:
    """What the stages know about the file going through them.

    active is the file the next stage works on: the staged copy on an apply, the
    source itself in a dry run. companions are the staged companion copies (their
    would-be paths in a dry run).
    """
    source: Path
    opts: RunOptions
    working_dir: WorkingDir
    active: Path
    companions: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    # The DateTimeOriginal organize dates the file by, so it never reads the file
    # again; a timestamp correction replaces it with the corrected value.
    organize_datetime: str = ""
    # tag's camera fields, written in the file's one metadata write: fix-timestamp's
    # when it runs, the provenance stage's otherwise.
    camera_fields: dict = field(default_factory=dict)
    corrected_time: Optional[str] = None
    # A dry run's --update-filename-dates rename that has not happened: the
    # would-be basename rides along for destination previews only.
    pending_rename: Optional[str] = None
    dest: Optional[str] = None
    organize_conflict: Optional[str] = None


@dataclass(frozen=True)
class StageOutcome:
    """A stage's result: whether it changed the file, or why it failed it."""
    changed: bool = False
    error: Optional[str] = None

    @property
    def failed(self) -> bool:
        return self.error is not None


class Stage:
    """One step of a file's trip.

    name is the stage_complete token; a stage with reports_completion False emits
    none (it is part of the step before it, as far as the app is concerned).
    """
    name = ""
    reports_completion = True

    def enabled(self, opts: RunOptions) -> bool:
        return True

    def run(self, ctx: FileContext) -> StageOutcome:
        raise NotImplementedError


def fix_writes_fields(opts: RunOptions) -> bool:
    """Whether every step's field writes, provenance included, go out in
    fix-timestamp's exiftool call, so the file is rewritten once. Otherwise
    ProvenanceStage makes that one write."""
    return opts.apply and FixTimestampStage().enabled(opts)


class IngestStage(Stage):
    """Copy the source file (and its companions) into the working directory."""
    name = "ingest"

    def run(self, ctx: FileContext) -> StageOutcome:
        opts, source = ctx.opts, ctx.source
        print("📥 Ingesting...", file=sys.stderr)
        ingest_companions = opts.companion_extensions if opts.copy_companion_files else None
        # Registered before the copy starts, so a cancel mid-ingest still knows
        # which partial copy to take with it.
        ctx.working_dir.stage([Path(ctx.working_dir.path) / source.name] if opts.apply else [])
        try:
            dest, action, companion_dests = ingest_media.ingest_file(
                str(source), ctx.working_dir.path, opts.apply, companion_extensions=ingest_companions,
            )
        except Exception as e:
            for line in str(e).split("\n"):
                if line.strip():
                    print(f"  {line}", file=sys.stderr)
            print(f"   ❌ Ingest failed for {source.name}", file=sys.stderr)
            return StageOutcome(error="Ingest failed")

        ctx.companions = companion_dests
        changed = action == "copied"
        if changed:
            ctx.active = Path(dest)
            ctx.working_dir.stage([Path(dest)] + [Path(c) for c in companion_dests])
            carry_exif_cache(str(source), dest)

        # The file's one metadata read (or the pre-flight's, carried to the copy
        # above). Taken before any step writes, so organize never reads the file
        # again.
        ctx.organize_datetime = read_exif_data(str(ctx.active)).get("DateTimeOriginal", "")

        if opts.copy_companion_files and companion_dests:
            for ext in opts.companion_extensions or []:
                companion_source = source.parent / (source.stem + ext)
                if companion_source.is_file():
                    ctx.source_files.append(str(companion_source))
        return StageOutcome(changed=changed)


class TagStage(Stage):
    """Finder tags and the profile's camera Make/Model."""
    name = TAG

    def enabled(self, opts: RunOptions) -> bool:
        if not opts.runs(TAG) or not opts.profile:
            return False
        make, model = self._camera(opts)
        return bool(self._finder_tags(opts) or make or model)

    @staticmethod
    def _finder_tags(opts: RunOptions) -> list:
        return tag_media.parse_tag_list(",".join((opts.profile or {}).get("tags", [])))

    @staticmethod
    def _camera(opts: RunOptions) -> tuple:
        exif = (opts.profile or {}).get("exif", {})
        return exif.get("make", ""), exif.get("model", "")

    def run(self, ctx: FileContext) -> StageOutcome:
        opts, active = ctx.opts, ctx.active
        make, model = self._camera(opts)
        print("🏷️  Tagging...", file=sys.stderr)
        # The camera fields ride in the file's one metadata write, fix-timestamp's or
        # the provenance stage's, so tagging never writes them itself.
        try:
            tag_result = tag_media.tag_media_file(
                str(active), self._finder_tags(opts), make or None, model or None,
                apply=opts.apply, write_exif=False)
        except MetadataWriteRefused as refusal:
            print(f"   ❌ exiftool could not write {active.name}: {refusal}", file=sys.stderr)
            return StageOutcome(error=str(refusal))
        if opts.apply:
            ctx.camera_fields = tag_media.camera_exif_fields(str(active), make or None, model or None)
        if tag_result is None:
            return StageOutcome()
        emit_event("tag_result",
            file=active.name,
            action=tag_result.action,
            tags_added=tag_result.tags_added,
            exif_make=tag_result.exif_make,
            exif_model=tag_result.exif_model,
            file_make=tag_result.file_make,
            file_model=tag_result.file_model,
        )
        return StageOutcome(changed=tag_result.action == "tagged")


class FixTimestampStage(Stage):
    """Correct the clock fields and birth time, writing other steps' fields too."""
    name = FIX_TIMESTAMP

    def enabled(self, opts: RunOptions) -> bool:
        return opts.runs(FIX_TIMESTAMP)

    def run(self, ctx: FileContext) -> StageOutcome:
        opts, active = ctx.opts, ctx.active
        print("🔧 Fixing timestamp...", file=sys.stderr)
        try:
            ts_result = fix_media_timestamp.fix_media_timestamps(
                str(active),
                apply=opts.apply,
                timezone_spec=opts.timezone_spec,
                infer_from_filename=opts.infer_from_filename,
                time_offset_seconds=opts.time_offset,
                force_timezone=opts.force_timezone,
                extra_write_fields=ctx.camera_fields,
                record_provenance=True,
            )
        except Exception as e:
            error_msg = str(e)
            print(f"   ❌ {error_msg}", file=sys.stderr)
            emit_event("timestamp_result",
                file=active.name,
                action="error",
                error=error_msg,
            )
            return StageOutcome(error=error_msg)

        emit_event("timestamp_result",
            file=active.name,
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
            reason=ts_result.reason,
        )

        if ts_result.timestamp_action == "error":
            print(f"   ❌ Timestamp fix failed for {ctx.source.name}", file=sys.stderr)
            return StageOutcome(error=ts_result.error or "Timestamp fix failed")

        ctx.corrected_time = ts_result.corrected_time
        if ts_result.corrected_time:
            ctx.organize_datetime = ts_result.corrected_time
        return StageOutcome(
            changed=ts_result.timestamp_action in ("would_fix", "fixed", "would_add", "added"))


class ProvenanceStage(Stage):
    """The camera fields and provenance in one exiftool call, when fix-timestamp is
    not running to carry them.

    Every file the pipeline moves gets a provenance record, so verify-card can find
    a copy by its card name after it has been renamed. Part of the step before it
    as far as the app is concerned, so it reports no stage_complete of its own.
    """
    name = "provenance"
    reports_completion = False

    def enabled(self, opts: RunOptions) -> bool:
        return opts.apply and not fix_writes_fields(opts)

    def run(self, ctx: FileContext) -> StageOutcome:
        file_path = str(ctx.active)
        exif = read_exif_data(file_path)
        provenance_args = provenance_field_args(file_path, exif)
        camera_args = [f"-{tag}={value}" for tag, value in ctx.camera_fields.items()]
        if not (provenance_args or camera_args):
            return StageOutcome()
        try:
            written = exiftool.write_tags(file_path, provenance_args + camera_args)
        except MetadataWriteRefused as refusal:
            written, error = False, str(refusal)
            print(f"   ❌ exiftool could not write this file: {error}", file=sys.stderr)
        else:
            error = None
        if written:
            return StageOutcome()
        # A failed camera write fails the file; a failed provenance-only write is a
        # warning, as it is in fix-timestamp.
        if camera_args:
            print(f"   ❌ Failed to write {', '.join(ctx.camera_fields)}", file=sys.stderr)
            return StageOutcome(error=error or f"Failed to write {', '.join(ctx.camera_fields)}")
        print("   ⚠️  Failed to record original filename and timestamps", file=sys.stderr)
        return StageOutcome()


class RenameStage(Stage):
    """--update-filename-dates: rename the file (and companions) to the corrected time.

    Part of fix-timestamp as far as the app is concerned, so it reports no
    stage_complete of its own.
    """
    name = "rename"
    reports_completion = False

    def enabled(self, opts: RunOptions) -> bool:
        return FixTimestampStage().enabled(opts) and opts.update_filename_dates

    def run(self, ctx: FileContext) -> StageOutcome:
        corrected_dt = parse_datetime_original(ctx.corrected_time) if ctx.corrected_time else None
        if not corrected_dt:
            return StageOutcome()
        active = ctx.active
        new_name = build_filename(active.name, corrected_dt)
        if not new_name or new_name == active.name:
            return StageOutcome()

        new_path = active.parent / new_name
        if ctx.opts.apply:
            os.rename(str(active), str(new_path))
            renamed_companions = []
            for ext in ctx.opts.companion_extensions or []:
                old_companion = active.parent / (active.stem + ext)
                if old_companion.is_file():
                    new_companion = active.parent / (new_path.stem + ext)
                    os.rename(str(old_companion), str(new_companion))
                    renamed_companions.append(str(new_companion))
            if renamed_companions:
                ctx.companions = renamed_companions
            ctx.working_dir.stage([new_path] + [Path(c) for c in ctx.companions])
        else:
            # The rename has not happened: active must keep pointing at the real
            # file, and only the destination preview carries the would-be name.
            print(f"  [DRY RUN] Would rename: {active.name} → {new_name}", file=sys.stderr)
            ctx.pending_rename = new_name
        emit_event("rename_result",
            file=active.name,
            renamed_to=new_name,
        )
        if ctx.opts.apply:
            ctx.active = new_path
        return StageOutcome()


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

_ORGANIZE_CHANGES = ("copied", "moved", "overwrote", "would_copy", "would_move", "would_overwrite")


class OutputStage(Stage):
    """Move the file into the target's date folders, its companions beside it."""
    name = "output"

    def run(self, ctx: FileContext) -> StageOutcome:
        opts, source, active = ctx.opts, ctx.source, ctx.active
        print("📁 Organizing by date...", file=sys.stderr)

        folder_template = opts.profile.get("folder_template") if opts.profile else None
        org_result = organize_by_date.process_file(
            str(active), opts.target_dir, folder_template or None, group=opts.group,
            copy_mode=False, overwrite=opts.overwrite, apply=opts.apply, verbose=opts.verbose,
            dest_name=ctx.pending_rename, datetime_original=ctx.organize_datetime,
        )
        staged_action = staged_organize_action(org_result.action)
        emit_event("organize_result",
            file=active.name,
            action=staged_action,
            dest=org_result.dest,
            reason=org_result.reason,
        )

        outcome_line = _OUTCOME_LINE.get(staged_action)
        if outcome_line:
            print(outcome_line.format(source=source, dest=org_result.dest), file=sys.stderr)

        # A file the destination already holds a different copy of is the one skip
        # --overwrite can resolve, so it is the only one the batch reports back.
        if (org_result.action == "skipped"
                and org_result.reason == organize_by_date.SKIP_EXISTS_DIFFERS):
            ctx.organize_conflict = active.name

        if org_result.action == "error":
            print(f"   ❌ Organization failed for {source.name}", file=sys.stderr)
            return StageOutcome(error="Organization failed")

        # A staged copy organize declined to place is a duplicate of a file already
        # at the destination, so it has no further use. Without this an idempotent
        # re-run stages the whole library into the working dir and leaves it there.
        if org_result.action == "skipped" and ctx.working_dir.staged:
            print(f"   Discarded staged copy of {source.name} "
                  f"(skipped: {org_result.reason})", file=sys.stderr)
            ctx.working_dir.discard()

        ctx.dest = org_result.dest
        if opts.copy_companion_files and ctx.companions and ctx.dest:
            self._move_companions(ctx, Path(ctx.dest).parent)
        ctx.working_dir.release()
        return StageOutcome(changed=org_result.action in _ORGANIZE_CHANGES)

    @staticmethod
    def _move_companions(ctx: FileContext, output_dir: Path) -> None:
        for companion_working_path in ctx.companions:
            companion_file = Path(companion_working_path)
            companion_target = output_dir / companion_file.name
            if ctx.opts.apply and companion_file.exists():
                os.makedirs(output_dir, exist_ok=True)
                shutil.move(str(companion_file), str(companion_target))
                print(f"  Companion: {companion_file.name} → {companion_target}", file=sys.stderr)
            elif not ctx.opts.apply:
                print(f"  [DRY RUN] Would move companion: {companion_file.name} → {companion_target}", file=sys.stderr)


class GyroflowStage(Stage):
    """A Gyroflow stabilization project beside the organized file."""
    name = GYROFLOW

    def enabled(self, opts: RunOptions) -> bool:
        profile_enabled = opts.profile.get("gyroflow_enabled", False) if opts.profile else False
        return bool(opts.runs(GYROFLOW) and profile_enabled and opts.gyroflow_config)

    def run(self, ctx: FileContext) -> StageOutcome:
        opts = ctx.opts
        config = opts.gyroflow_config or {}
        print("🎥 Generating gyroflow project...", file=sys.stderr)
        gyroflow_file = Path(ctx.dest) if ctx.dest and opts.apply else ctx.active
        gf_result = generate_gyroflow.generate_gyroflow_project(
            gyroflow_file, opts.apply, binary=config.get("binary"),
            preset_json=json.dumps(config.get("preset", {})))
        emit_event("gyroflow_result",
            file=ctx.active.name,
            action=gf_result.action,
            gyroflow_path=gf_result.gyroflow_path,
            error=gf_result.error,
        )
        return StageOutcome(changed=gf_result.action == "generated")


STAGES: list[Stage] = [
    IngestStage(), TagStage(), ProvenanceStage(), FixTimestampStage(), RenameStage(), OutputStage(),
    GyroflowStage(),
]


def enabled_stages(opts: RunOptions) -> list[Stage]:
    """The stages a run with these options takes every file through, in order."""
    return [stage for stage in STAGES if stage.enabled(opts)]


@dataclass
class FileResult:
    """One file's outcome, for the batch's counts and its archive step."""
    changed: bool = False
    error: Optional[str] = None
    source_files: list[str] = field(default_factory=list)
    organize_conflict: Optional[str] = None

    @property
    def failed(self) -> bool:
        return self.error is not None


def process_file(source: Path, opts: RunOptions, working_dir: WorkingDir) -> FileResult:
    """Take one file through every enabled stage; the first failure ends its trip.

    A failed file's staged copy is released, not deleted: the batch keeps the
    working dir for inspection.
    """
    emit_event("pipeline_file", file=source.name, source_path=str(source))
    ctx = FileContext(source=source, opts=opts, working_dir=working_dir, active=source,
                      source_files=[str(source)])
    changed = False
    for stage in enabled_stages(opts):
        outcome = stage.run(ctx)
        if outcome.failed:
            working_dir.release()
            emit_event("pipeline_result", file=source.name, result="failed")
            return FileResult(error=outcome.error, source_files=ctx.source_files)
        changed = changed or outcome.changed
        if stage.reports_completion:
            emit_event("stage_complete", stage=stage.name)

    if changed:
        emit_event("pipeline_result", file=source.name, result="changed" if opts.apply else "would_change")
    else:
        emit_event("pipeline_result", file=source.name, result="unchanged")
    return FileResult(changed=changed, source_files=ctx.source_files,
                      organize_conflict=ctx.organize_conflict)
