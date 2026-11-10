"""Command-line helpers shared by the scripts' entry points."""

from __future__ import annotations

import argparse
import signal
import sys
from typing import Callable, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from lib.countries import get_timezone_for_country
from lib.exiftool import exiftool
from lib.timestamps.sources import is_zone_name

# ---------------------------------------------------------------------------
# Interrupts
# ---------------------------------------------------------------------------

# Cancel in the app is SIGTERM and Ctrl+C in a terminal is SIGINT; both mean the
# same thing.
SIGNAL_MESSAGES = {
    signal.SIGINT: "\n\nInterrupted by user",
    signal.SIGTERM: "\n\nCancelled",
}


def interrupt_handler(cleanup: Optional[Callable[[], None]] = None):
    """A signal handler that shuts exiftool down, runs cleanup, then exits 128+sig.

    A script owns a persistent ``exiftool -stay_open`` process. Under the default
    SIGTERM disposition the interpreter dies without unwinding, so that process is
    re-parented and keeps running; closing it here stops it instead. cleanup runs
    only once it has returned, when nothing is still writing.
    """
    def handler(sig, frame):  # noqa: ARG001
        print(SIGNAL_MESSAGES[sig], file=sys.stderr)
        exiftool.close()
        if cleanup is not None:
            cleanup()
        sys.exit(128 + sig)
    return handler


def install_interrupt_handlers(handler=None) -> None:
    """Route SIGINT and SIGTERM to handler (by default, interrupt_handler())."""
    handler = handler or interrupt_handler()
    for sig in SIGNAL_MESSAGES:
        signal.signal(sig, handler)


# ---------------------------------------------------------------------------
# Timezone arguments
# ---------------------------------------------------------------------------

VALUE_OPTIONS_ACCEPTING_NEGATIVES = ('--timezone', '--time-offset')


def attach_negative_option_values(argv):
    """Rewrite '--timezone -05:00' as '--timezone=-05:00'.

    argparse before Python 3.13 reads any value starting with '-' that is not a
    plain number as another flag, so western offsets are rejected outright.
    """
    normalized = []
    argv = list(argv)
    index = 0
    while index < len(argv):
        arg = argv[index]
        value = argv[index + 1] if index + 1 < len(argv) else None
        if arg in VALUE_OPTIONS_ACCEPTING_NEGATIVES and value is not None and value.startswith('-'):
            normalized.append(f"{arg}={value}")
            index += 2
            continue
        normalized.append(arg)
        index += 1
    return normalized


def add_timezone_args(parser: argparse.ArgumentParser, location_flag: str) -> None:
    """Add --timezone and the script's location flag, stored as args.location.

    Scripts keep the flag name they have always had (--location, --country); what
    each accepts is the same.
    """
    parser.add_argument(
        "--timezone",
        help="IANA zone name (e.g., Pacific/Auckland), resolved per file so a run spanning "
             "a DST changeover gets the right offset either side, or a fixed offset "
             "(e.g., +0800, +08:00, -05:00)")
    parser.add_argument(
        location_flag, dest="location",
        help="Country code or name to look the timezone up from when --timezone is not "
             "given (e.g., JP, Taiwan)")


class UnknownTimezone(ValueError):
    """--timezone named no zone the database has."""


class UnknownLocation(ValueError):
    """The location flag named no country with a known zone."""


def resolve_timezone(timezone: Optional[str], location: Optional[str]) -> Optional[str]:
    """The timezone spec a run uses: --timezone as given, else the location's offset.

    --timezone is an IANA zone name or a fixed offset in any of +HHMM, +HH:MM, HHMM
    (offsets are normalized where they are resolved). Raises UnknownTimezone for a
    zone name the database lacks and UnknownLocation for a location with no zone;
    returns None when neither is given.
    """
    if timezone:
        if is_zone_name(timezone):
            try:
                ZoneInfo(timezone)
            except (ZoneInfoNotFoundError, ValueError):
                raise UnknownTimezone(timezone)
        return timezone
    if location:
        offset = get_timezone_for_country(location)
        if not offset:
            raise UnknownLocation(location)
        return offset
    return None
