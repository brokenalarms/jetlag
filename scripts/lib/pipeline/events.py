"""The pipeline's JSONL events on stdout; scripts/pipeline-schema.yaml defines them."""

from __future__ import annotations

import json
import sys

_machine_output = not sys.stdout.isatty()


def emit_event(event_type: str, **fields) -> None:
    """Emit a JSONL event to stdout.

    Only emits when stdout is a pipe (macOS app), not a terminal (CLI).
    Flushes immediately so the app receives each line without buffering.

    None values are omitted. Lists, bools, and numbers stay as native JSON types.
    """
    if not _machine_output:
        return
    payload: dict = {"event": event_type}
    for key, value in fields.items():
        if value is None:
            continue
        payload[key] = value
    print(json.dumps(payload), flush=True)
