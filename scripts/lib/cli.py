"""Command-line helpers shared by the scripts' entry points."""

from __future__ import annotations


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
