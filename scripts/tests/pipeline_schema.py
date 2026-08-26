"""Validator for JSONL pipeline events against scripts/pipeline-schema.yaml.

The schema is the one place a token is defined. This module lets the test suite
hold the emitting side to it: any event media-pipeline.py writes to stdout must
declare every field it carries and stay inside the enumerations. A token added to
the script without being declared here fails, and so does a declared-but-unemitted
required field.

Not a test module itself — imported by the tests that capture pipeline output.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

SCHEMA_PATH = Path(__file__).parent.parent / "pipeline-schema.yaml"

_TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "list[string]": lambda v: isinstance(v, list) and all(isinstance(i, str) for i in v),
    "map[string, list[string]]": lambda v: (
        isinstance(v, dict)
        and all(isinstance(k, str) for k in v)
        and all(isinstance(i, str) for vals in v.values() for i in vals)
    ),
}


def load_schema() -> dict[str, Any]:
    with open(SCHEMA_PATH) as f:
        return yaml.safe_load(f)["events"]


def enum_tokens(event_type: str, field: str) -> list[str]:
    """The tokens a field may carry, as declared in the schema."""
    return load_schema()[event_type]["fields"][field]["enum"]


def validate_event(event: dict, schema: dict[str, Any] | None = None) -> None:
    """Raise AssertionError describing the first way `event` departs from the schema."""
    schema = schema if schema is not None else load_schema()

    event_type = event.get("event")
    assert event_type in schema, \
        f"Actual: event={event_type!r}, Expected: one of {sorted(schema)} (declare it in pipeline-schema.yaml)"

    fields = schema[event_type]["fields"]

    undeclared = set(event) - {"event"} - set(fields)
    assert not undeclared, \
        f"Actual: {event_type} carries undeclared field(s) {sorted(undeclared)}, " \
        f"Expected: only {sorted(fields)} (declare them in pipeline-schema.yaml)"

    for name, spec in fields.items():
        if name not in event:
            assert spec.get("optional"), \
                f"Actual: {event_type} is missing required field {name!r}, Expected: present"
            continue

        value = event[name]
        check = _TYPE_CHECKS.get(spec["type"])
        assert check is not None, \
            f"Schema declares unknown type {spec['type']!r} for {event_type}.{name}"
        assert check(value), \
            f"Actual: {event_type}.{name}={value!r} ({type(value).__name__}), " \
            f"Expected: {spec['type']}"

        allowed = spec.get("enum")
        assert allowed is None or value in allowed, \
            f"Actual: {event_type}.{name}={value!r}, Expected: one of {allowed} " \
            f"(add the token to pipeline-schema.yaml and to the app's mapping)"


def validate_events(events: list[dict]) -> list[dict]:
    """Validate a whole JSONL capture, returning it so callers can chain."""
    schema = load_schema()
    for event in events:
        validate_event(event, schema)
    return events
