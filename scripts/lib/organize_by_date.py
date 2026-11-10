"""Move (or copy) one file into a date-based directory structure.

The date is the file's own, from the timestamp hierarchy
(FileReading.date_folder() in lib/timestamps/sources.py) in the declared
timezone, or the date a caller already holds for it.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from typing import Optional

from lib.timestamps.sources import read_file


@dataclass
class OrganizeResult:
    """What the organize step did, as tokens the caller renders verbatim.

    `reason` explains a skip and is set only when the file was not moved. Its
    tokens are enumerated in pipeline-schema.yaml alongside `action`; nothing
    downstream may re-derive either from the presence of `dest`.
    """
    dest: str
    action: str
    reason: Optional[str] = None

MONTH_ABBREVS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# The folder a file goes to when its caller names no template: a group folder
# after the year when there is a group, none when there is not.
DEFAULT_FOLDER_TEMPLATE = "{{YYYY}}/{{GROUP}}/{{YYYY}}-{{MM}}-{{DD}}"


def expand_path_template(template: Optional[str], file_date: str,
                         group: Optional[str] = None) -> str:
    """Expand path template with date components.

    Template variables: {{YYYY}}, {{MM}}, {{MMM}}, {{DD}}, {{YYYY-MM-DD}}, {{GROUP}}
    file_date: YYYY-MM-DD format

    template None means DEFAULT_FOLDER_TEMPLATE. A group fills {{GROUP}}; the
    group is an optional grouping folder, so without one that folder is left out.
    """
    if template is None:
        template = DEFAULT_FOLDER_TEMPLATE
    template = template.replace("{{GROUP}}", group or "")

    year = file_date[:4]
    month = file_date[5:7]
    day = file_date[8:10]
    month_abbr = MONTH_ABBREVS[int(month)]

    expanded = template
    expanded = expanded.replace('{{YYYY}}', year)
    expanded = expanded.replace('{{MM}}', month)
    expanded = expanded.replace('{{MMM}}', month_abbr)
    expanded = expanded.replace('{{DD}}', day)
    expanded = expanded.replace('{{YYYY-MM-DD}}', file_date)

    # Without a group its folder is empty: drop it, and any other empty folder.
    return "/".join(folder for folder in expanded.split("/") if folder)


SKIP_IDENTICAL = "identical"
SKIP_EXISTS_DIFFERS = "exists_differs"
SKIP_USER_CHOICE = "user_choice"


def _skip_explanation(reason: Optional[str], src_size: int, dst_size: int) -> str:
    """Human phrasing for a skip token. The token is the data; this is display."""
    if reason == SKIP_IDENTICAL:
        return f"identical, {src_size / 1048576:.1f} MB"
    if reason == SKIP_USER_CHOICE:
        return "user choice"
    return f"exists at destination, different size: src {src_size} bytes, dst {dst_size} bytes"


def _handle_existing_target(file_path, target_file, target_path, abs_target,
                            base, organized_path, copy_mode, overwrite, apply):
    """Handle case where target file already exists."""
    src_size = os.path.getsize(file_path)
    dst_size = os.path.getsize(target_file)

    skip_reason = None

    if overwrite:
        action = "overwrite"
    elif src_size == dst_size:
        action = "skip"
        skip_reason = SKIP_IDENTICAL
    elif apply:
        print(f"\u26a0\ufe0f  File exists: {base}", file=sys.stderr)
        print(f"   Source: {src_size} bytes, Dest: {dst_size} bytes", file=sys.stderr)
        action = "skip"
        skip_reason = SKIP_EXISTS_DIFFERS
        # Prompt only when a real terminal is attached. Reading /dev/tty from a
        # background process group does not raise \u2014 the kernel SIGTTIN-stops the
        # entire group, freezing any non-interactive runner (tests, the app, a
        # supervisor) until its timeout. The OSError/EOFError fallback cannot
        # catch that, so the tty read must be gated on an actual terminal.
        if sys.stderr.isatty():
            try:
                sys.stderr.write("   (o)verwrite / (s)kip? ")
                sys.stderr.flush()
                with open('/dev/tty') as tty:
                    choice = tty.readline().strip()
                # An answer was read back, so the outcome is now the user's,
                # whichever way it went.
                action = "overwrite" if choice.lower().startswith('o') else "skip"
                skip_reason = SKIP_USER_CHOICE
            except (OSError, EOFError):
                pass
        else:
            print("   No terminal attached \u2014 skipping (use --overwrite to replace)", file=sys.stderr)
    else:
        action = "skip"
        skip_reason = SKIP_EXISTS_DIFFERS

    if action == "overwrite":
        if apply:
            os.makedirs(target_path, exist_ok=True)
            transfer = shutil.copy2 if copy_mode else shutil.move
            transfer(file_path, target_file)
            print(f"\u267b\ufe0f  Overwrote: {base} \u2192 {organized_path}/", file=sys.stderr)
            return OrganizeResult(dest=abs_target, action="overwrote")
        print(f"[DRY RUN] Would overwrite: {file_path} \u2192 {abs_target}", file=sys.stderr)
        return OrganizeResult(dest=abs_target, action="would_overwrite")

    print(f"\u23ed\ufe0f  Skipped ({_skip_explanation(skip_reason, src_size, dst_size)}): {base}",
          file=sys.stderr)

    return OrganizeResult(dest=abs_target, action="skipped", reason=skip_reason)


def process_file(file_path: str, target_dir: str, template: Optional[str],
                 copy_mode: bool, overwrite: bool, apply: bool,
                 verbose: bool, dest_name: Optional[str] = None,
                 file_date: Optional[str] = None,
                 group: Optional[str] = None,
                 timezone_spec: Optional[str] = None) -> OrganizeResult:
    """Process a single file for organization.

    Printed messages name file_path: they report the operation this function
    performed, on the file it was handed. A caller that staged a copy states
    the outcome for the original in a line of its own.

    dest_name overrides the basename used to build the destination path — for a
    dry run previewing a rename that has not happened, the destination carries
    the name apply will produce while every read still uses the real file_path.

    file_date, when given, is the 'YYYY-MM-DD' the destination is built from in
    place of reading the file; otherwise the file's own date is read in
    timezone_spec, the zone the footage was shot in.

    template and group are as expand_path_template() takes them.

    Returns:
        OrganizeResult with dest path and action taken
    """
    base = dest_name or os.path.basename(file_path)

    if verbose:
        print(f"Processing: {file_path}", file=sys.stderr)

    if file_date is None:
        file_date = read_file(file_path).date_folder(timezone_spec)
    if not file_date:
        print(f"ERROR: Cannot determine date for {base}", file=sys.stderr)
        return OrganizeResult(dest="", action="error")

    if verbose:
        print(f"  Date: {file_date}", file=sys.stderr)

    organized_path = expand_path_template(template, file_date, group)

    target_path = os.path.join(target_dir.rstrip('/'), organized_path.lstrip('/'))
    target_file = os.path.join(target_path, base)

    if os.path.isabs(target_file):
        abs_target = target_file
    else:
        abs_target = os.path.join(os.getcwd(), target_file.lstrip('./'))

    # Check if file is already in correct location
    file_realdir = os.path.dirname(os.path.realpath(file_path))
    try:
        target_realpath = os.path.realpath(target_path)
    except OSError:
        target_realpath = target_path

    if file_realdir == target_realpath:
        print(f"\u2713 Already organized: {base} ({organized_path})", file=sys.stderr)
        return OrganizeResult(dest=abs_target, action="skipped")

    if os.path.exists(target_file):
        return _handle_existing_target(
            file_path, target_file, target_path, abs_target, base,
            organized_path, copy_mode, overwrite, apply
        )

    if apply:
        os.makedirs(target_path, exist_ok=True)
        if copy_mode:
            shutil.copy2(file_path, target_file)
            print(f"\u2705 Copied: {file_path} \u2192 {abs_target}", file=sys.stderr)
            return OrganizeResult(dest=abs_target, action="copied")
        else:
            shutil.move(file_path, target_file)
            print(f"\u2705 Moved: {file_path} \u2192 {abs_target}", file=sys.stderr)
            return OrganizeResult(dest=abs_target, action="moved")
    else:
        if copy_mode:
            print(f"[DRY RUN] Would copy: {file_path} \u2192 {abs_target}", file=sys.stderr)
            return OrganizeResult(dest=abs_target, action="would_copy")
        else:
            print(f"[DRY RUN] Would move: {file_path} \u2192 {abs_target}", file=sys.stderr)
            return OrganizeResult(dest=abs_target, action="would_move")
