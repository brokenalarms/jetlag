#!/usr/bin/env python3
"""
Check that every file on a card is on each backup location, before the card is wiped.

Output is JSONL on stdout, one event per line, declared in lib/verify-card-schema.yaml:
verify_location per location, then verify_file and one verify_result per location for
each checked card file, then verify_summary. The logic is in lib/verify_card.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lib.command_line import install_interrupt_handlers
from lib.exiftool import exiftool
from lib.verify_card import parse_location, verify_card


def emit(event: str, **fields) -> None:
    print(json.dumps({"event": event, **{k: v for k, v in fields.items() if v is not None}}),
          flush=True)


def location_arg(spec: str) -> tuple[str, str]:
    try:
        return parse_location(spec)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from None


def main() -> int:
    install_interrupt_handlers()
    parser = argparse.ArgumentParser(
        prog="verify-card.sh",
        description="Check that every file on a card is on each backup location")
    parser.add_argument("source", help="Folder to check, usually the card root")
    parser.add_argument("--location", action="append", type=location_arg, required=True,
                        metavar="NAME=ROOT",
                        help="A backup location to check against; repeat for each")
    parser.add_argument("--media-extensions", nargs="+", required=True,
                        help="Extensions of files that must be on every location")
    parser.add_argument("--companion-extensions", nargs="*", default=[],
                        help="Extensions of companion files (.lrv, .thm ...)")
    parser.add_argument("--include-companions", action="store_true",
                        help="Require companion files on every location too")
    parser.add_argument("--ignore-paths", nargs="*", default=[],
                        help="Folder names whose contents are not checked (e.g. MISC)")
    args = parser.parse_args()

    source = Path(args.source)
    if not source.is_dir():
        print(f"ERROR: {source} is not a folder", file=sys.stderr)
        return 1
    names = [name for name, _ in args.location]
    if len(set(names)) != len(names):
        print("ERROR: each backup location needs its own name", file=sys.stderr)
        return 1

    report = verify_card(source, args.location, args.media_extensions,
                         args.companion_extensions, args.include_companions, args.ignore_paths)

    for location in report.locations:
        emit("verify_location", location=location.name, root=location.root,
             remote=location.remote, reachable=location.reachable,
             files=len(location.entries) if location.reachable else None)
    for card_file in report.scan.checked:
        emit("verify_file", file=card_file.rel, kind=card_file.kind, size=card_file.size,
             data_bytes=card_file.data_bytes)
        for location_name, result in report.verdicts[card_file.rel].items():
            emit("verify_result", file=card_file.rel, location=location_name,
                 verdict=result.verdict, basis=result.basis, copies=result.copies)

    checked = len(report.scan.checked)
    emit("verify_summary", checked=checked, on_every_location=report.on_every_location,
         need_attention=checked - report.on_every_location, not_checked=report.scan.not_checked,
         not_checked_kinds=sorted(report.scan.not_checked_kinds))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        exiftool.close()
