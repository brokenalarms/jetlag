"""Checks over the whole batch before the first file is processed.

Every check is declared the same way in CHECKS and run by run_checks(), which
emits one batch_check event per finding and stops the run once, after every
check has reported, so one answer covers them all.
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from lib import ingest_media, tag_media
from lib.media_pipeline.consent import require_consent
from lib.media_pipeline.events import emit_event
from lib.media_pipeline.options import RunOptions
from lib.timestamps.sources import normalize_timezone_input, read_file


def check_stale_exiftool_tmp(source_dir: str) -> None:
    """Stop on exiftool_tmp directories left by a crashed run: exiftool fails
    silently beside one. A terminal is offered to delete them."""
    tmp_dirs = list(Path(source_dir).rglob("exiftool_tmp"))
    if not tmp_dirs:
        return
    print(f"⚠️  Found {len(tmp_dirs)} stale exiftool_tmp director{'y' if len(tmp_dirs) == 1 else 'ies'} in source:", file=sys.stderr)
    for d in tmp_dirs:
        print(f"   {d}", file=sys.stderr)
    print(file=sys.stderr)

    require_consent(
        False, "Delete them? This will allow exiftool to run.",
        ["ERROR: Cannot proceed - exiftool will fail with these directories present.",
         "Delete the directories listed above, or re-run from a terminal to be prompted."],
        declined_line="ERROR: Cannot proceed - exiftool will fail with these directories present",
    )
    for d in tmp_dirs:
        shutil.rmtree(d)
    print("✅ Deleted exiftool_tmp directories", file=sys.stderr)


REFUSES_APPLY = "apply"
REFUSES_ALWAYS = "always"
REFUSES_NEVER = "never"

NO_ZONE = "none"


@dataclass(frozen=True)
class Finding:
    """What a check found: the files, and for a check that splits the batch,
    the files under each label (a zone, a camera), in file order. chosen is
    what the files were held against, in the same terms as the labels: the
    offsets --timezone gives them, so a zone name compares as an offset."""
    files: list[str]
    groups: dict[str, list[str]] = field(default_factory=dict)
    chosen: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BatchCheck:
    """One batch-level check, declared as data.

    refuses says which runs stop on a finding: an apply, every run, or none (a
    finding made after the batch, which only a re-run can act on). assent_flag
    lets a refused run go on; a check without one always stops. find is pure
    over the files' cached reads; a check without one is reported by whatever
    makes its finding. headline, note and prompt are its lines on stderr and
    its question on a terminal.
    """
    token: str
    assent_flag: Optional[str]
    refuses: str
    headline: str
    note: str = ""
    prompt: str = ""
    applies: Callable[[RunOptions], bool] = lambda opts: True
    find: Optional[Callable[[list[Path], RunOptions], Optional[Finding]]] = None

    def granted(self, opts: RunOptions) -> bool:
        """Whether the assent flag was given: its RunOptions field is argparse's dest."""
        if self.assent_flag is None:
            return False
        return bool(getattr(opts, self.assent_flag.removeprefix("--").replace("-", "_")))

    def refused(self, opts: RunOptions) -> bool:
        if self.refuses == REFUSES_NEVER:
            return False
        if self.refuses == REFUSES_APPLY and not opts.apply:
            return False
        return not self.granted(opts)


def _grouped(pairs) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for label, name in pairs:
        groups.setdefault(label, []).append(name)
    return groups


def find_protected_sources(files: list[Path], opts: RunOptions) -> Optional[Finding]:
    protected = [fp.name for fp in files if ingest_media.is_protected(str(fp))]
    return Finding(protected) if protected else None


def _profile_camera(opts: RunOptions) -> tuple[Optional[str], Optional[str]]:
    expected = (opts.profile or {}).get("exif") or {}
    return expected.get("make"), expected.get("model")


def find_camera_mismatch(files: list[Path], opts: RunOptions) -> Optional[Finding]:
    """Files whose Make/Model differ from the profile's, grouped by the camera
    they name: the profile was likely picked for the wrong body."""
    make, model = _profile_camera(opts)
    pairs = []
    for fp in files:
        found = tag_media.camera_mismatch(str(fp), make, model)
        if found:
            pairs.append((" ".join(found.values()), fp.name))
    if not pairs:
        return None
    return Finding([name for _, name in pairs], _grouped(pairs))


def _zone_label(zone: Optional[str]) -> str:
    return normalize_timezone_input(zone).replace(":", "") if zone else NO_ZONE


def find_mixed_timezones(files: list[Path], opts: RunOptions) -> Optional[Finding]:
    """The batch split by FileReading.zone. A file with no zone evidence falls in
    the none group, so zoned and unzoned files together are mixed."""
    groups = _grouped((_zone_label(read_file(str(fp)).zone), fp.name) for fp in files)
    if len(groups) < 2:
        return None
    return Finding([fp.name for fp in files], groups)


def find_zone_relabel(files: list[Path], opts: RunOptions) -> Optional[Finding]:
    """Files whose zoned tag differs from the zone --timezone gives them, grouped
    by the tag's zone. A zone name resolves per file, so each file is compared
    with the offset that zone had when it was shot. A camera zone setting that
    differs is not one: relabelling it is what the correction is for."""
    pairs = []
    chosen = []
    for fp in files:
        reading = read_file(str(fp))
        tagged = reading.tagged_zone
        expected = reading.declared_offset(opts.timezone_spec)
        if tagged and expected and _zone_label(tagged) != _zone_label(expected):
            pairs.append((_zone_label(tagged), fp.name))
            if _zone_label(expected) not in chosen:
                chosen.append(_zone_label(expected))
    if not pairs:
        return None
    return Finding([name for _, name in pairs], _grouped(pairs), chosen)


def find_filename_unparseable(files: list[Path], opts: RunOptions) -> Optional[Finding]:
    unparseable = [fp.name for fp in files if read_file(str(fp)).filename_timestamp is None]
    return Finding(unparseable) if unparseable else None


CHECKS: list[BatchCheck] = [
    BatchCheck(
        token="protected_sources",
        find=find_protected_sources,
        assent_flag="--unlock-protected",
        refuses=REFUSES_APPLY,
        headline="source file(s) are protected (locked)",
        note="Their imported copies will be unlocked; the source files stay locked.",
        prompt="Import them unlocked?",
    ),
    BatchCheck(
        token="camera_mismatch",
        applies=lambda opts: any(_profile_camera(opts)),
        find=find_camera_mismatch,
        assent_flag="--allow-camera-mismatch",
        refuses=REFUSES_APPLY,
        headline="file(s) were not shot on this profile's camera",
        note="Their camera fields are left as the camera wrote them.",
        prompt="Import them anyway?",
    ),
    BatchCheck(
        token="mixed_timezones",
        applies=lambda opts: not opts.infer_from_filename,
        find=find_mixed_timezones,
        assent_flag="--allow-mixed-timezones",
        refuses=REFUSES_ALWAYS,
        headline="file(s) span more than one timezone",
        note="Consider processing each timezone group separately.",
        prompt="Process them together anyway?",
    ),
    BatchCheck(
        token="zone_relabel",
        applies=lambda opts: not opts.infer_from_filename,
        find=find_zone_relabel,
        assent_flag="--force-timezone",
        refuses=REFUSES_APPLY,
        headline="file(s) carry a timezone that differs from --timezone",
        note="The embedded timezone is usually correct (set by the camera).",
        prompt="Relabel them to the timezone given?",
    ),
    BatchCheck(
        token="filename_unparseable",
        applies=lambda opts: opts.infer_from_filename,
        find=find_filename_unparseable,
        assent_flag=None,
        refuses=REFUSES_ALWAYS,
        headline="file(s) have no timestamp in their name for --infer-from-filename",
    ),
]

DESTINATION_OCCUPIED = BatchCheck(
    token="destination_occupied",
    assent_flag="--overwrite",
    refuses=REFUSES_NEVER,
    headline="file(s) already at the destination with different contents",
    note="They were left in place.",
)

ALL_CHECKS: list[BatchCheck] = [*CHECKS, DESTINATION_OCCUPIED]


def report_finding(check: BatchCheck, finding: Finding, opts: RunOptions) -> None:
    """The finding as one batch_check event, and as lines on stderr."""
    refused = check.refused(opts)
    print(f"⚠️  {len(finding.files)} {check.headline}:", file=sys.stderr)
    if finding.chosen:
        print(f"   chosen: {', '.join(finding.chosen)}", file=sys.stderr)
    if finding.groups:
        for label, names in finding.groups.items():
            print(f"   {label}: {', '.join(names)}", file=sys.stderr)
    else:
        for name in finding.files:
            print(f"   {name}", file=sys.stderr)
    if check.note:
        print(check.note, file=sys.stderr)
    if check.assent_flag and not check.granted(opts):
        if check.refuses == REFUSES_APPLY and not opts.apply:
            print(f"Previewing anyway; applying asks first (or pass {check.assent_flag}).",
                  file=sys.stderr)
        else:
            print(f"Re-run with {check.assent_flag} to go on with them.", file=sys.stderr)
    print(file=sys.stderr)
    emit_event("batch_check",
        check=check.token,
        files=finding.files,
        groups=finding.groups or None,
        chosen=finding.chosen or None,
        assent_flag=check.assent_flag,
        refused=refused,
    )


def run_checks(files: list[Path], opts: RunOptions) -> None:
    """Every check over the batch, in the order the user meets them. Every
    finding is reported before the run stops, so one re-run answers them all."""
    findings = []
    for check in CHECKS:
        if check.find is None or not check.applies(opts):
            continue
        finding = check.find(files, opts)
        if finding:
            findings.append((check, finding))
    for check, finding in findings:
        report_finding(check, finding, opts)

    refused = [check for check, _ in findings if check.refused(opts)]
    if any(check.assent_flag is None for check in refused):
        print("ERROR: Cannot proceed with the files listed above.", file=sys.stderr)
        sys.exit(1)
    for check in refused:
        require_consent(False, check.prompt, [
            f"ERROR: Cannot proceed: {check.headline}.",
            f"Re-run with {check.assent_flag}, or from a terminal to be prompted.",
        ])
