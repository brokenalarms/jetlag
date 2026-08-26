#!/usr/bin/env python3
"""
Contract tests binding media-pipeline's JSONL output to scripts/pipeline-schema.yaml.

The app renders emitted tokens 1:1 and never re-derives an outcome from whether a
field is populated. That only holds if the token set is pinned: these tests fail
when the pipeline emits a field or token the schema does not declare, and the
matching Swift tests (PipelineSchemaContractTests) fail when the schema declares an
organize_result token the app cannot label. Adding a token on one side only breaks
one of the two.

Run with: pytest tests/test_pipeline_schema.py -v
"""

import json

import pytest

from conftest import create_test_video
from pipeline_schema import enum_tokens, load_schema, validate_event, validate_events
# The pipeline harness and its profile isolation live with the pipeline tests;
# re-exporting the fixtures here is what makes them resolvable in this module.
from test_media_pipeline import run_pipeline, temp_workspace, test_profile  # noqa: F401


def _events(stdout: str) -> list[dict]:
    return [json.loads(line) for line in stdout.strip().split("\n") if line.strip()]


class TestSchemaIsSelfConsistent:
    """The schema's own examples are the fixtures both sides decode, so they must be valid."""

    def test_every_declared_example_validates_against_its_declaration(self):
        """A bad example would hand the Swift decoding test a fixture that proves nothing."""
        schema = load_schema()
        for event_type, spec in schema.items():
            example = spec.get("example")
            assert example is not None, \
                f"Actual: {event_type} has no example, Expected: a decodable fixture for the app tests"
            assert example.get("event") == event_type, \
                f"Actual: {event_type}.example.event={example.get('event')!r}, Expected: {event_type!r}"
            validate_event(example, schema)

    def test_organize_skip_reasons_are_enumerated(self):
        """The skip reason is data with a closed token set, not free-form prose."""
        assert set(enum_tokens("organize_result", "reason")) == \
            {"identical", "exists_differs", "user_choice"}


class TestEmittedEventsMatchSchema:
    """Everything the pipeline actually writes to stdout has to be declared."""

    def _run(self, workspace, test_profile, *extra):
        return run_pipeline([
            "--profile", test_profile,
            "--source", str(workspace["source"]),
            "--target", str(workspace["target"]),
            "--timezone", "+0900",
            "--group", "Test",
            *extra,
        ])

    def test_dry_run_events_all_validate(self, temp_workspace, test_profile):
        """A whole dry run's event stream is schema-clean, field by field and token by token."""
        create_test_video(temp_workspace["source"] / "test.mp4",
                          media_create_date="2025:10:05 01:00:00")

        result = self._run(temp_workspace, test_profile)

        events = validate_events(_events(result.stdout))
        assert {e["event"] for e in events} >= {"pipeline_file", "timestamp_result",
                                                "organize_result", "pipeline_result"}, \
            f"Actual: {sorted({e['event'] for e in events})}, Expected: the core per-file events"

    def test_apply_events_all_validate(self, temp_workspace, test_profile):
        """Applying emits a different token set (fixed/moved/changed) — also schema-clean."""
        create_test_video(temp_workspace["source"] / "test.mp4",
                          media_create_date="2025:10:05 01:00:00")

        result = self._run(temp_workspace, test_profile, "--apply")

        events = validate_events(_events(result.stdout))
        organize = next(e for e in events if e["event"] == "organize_result")
        assert organize["action"] == "moved", \
            f"Actual: organize_result.action={organize['action']!r}, Expected: 'moved'"

    def test_skip_against_existing_destination_carries_a_declared_reason(self, temp_workspace, test_profile):
        """The Korea dry run: destination holds a different-sized copy already.

        The event has to say skipped *and* say why, using a token the schema
        declares — this is the field the app reads instead of inferring a move
        from the presence of dest.
        """
        create_test_video(temp_workspace["source"] / "test.mp4",
                          media_create_date="2025:10:05 01:00:00")
        self._run(temp_workspace, test_profile, "--apply")

        organized = next(temp_workspace["target"].rglob("test.mp4"))
        with open(organized, "ab") as f:
            f.write(b"x" * 100)
        create_test_video(temp_workspace["source"] / "test.mp4",
                          media_create_date="2025:10:05 01:00:00")

        result = self._run(temp_workspace, test_profile)

        events = validate_events(_events(result.stdout))
        organize = next(e for e in events if e["event"] == "organize_result")
        assert organize["action"] == "skipped", \
            f"Actual: organize_result.action={organize['action']!r}, Expected: 'skipped'"
        assert organize["reason"] == "exists_differs", \
            f"Actual: organize_result.reason={organize.get('reason')!r}, Expected: 'exists_differs'"
        assert organize.get("dest"), \
            "A skipped file still reports where it would have gone — the app must not read that as a move"

    def test_undeclared_token_is_rejected(self):
        """The guard itself: a token the schema does not list fails validation.

        Without this, a new action added to the script and never declared would
        sail through every other test in this file.
        """
        with pytest.raises(AssertionError, match="organize_result.action"):
            validate_event({
                "event": "organize_result",
                "file": "test.mp4",
                "action": "relocated",
                "dest": "/tmp/test.mp4",
            })

    def test_undeclared_field_is_rejected(self):
        """A field the app has no decoding for must not appear unannounced."""
        with pytest.raises(AssertionError, match="undeclared field"):
            validate_event({
                "event": "organize_result",
                "file": "test.mp4",
                "action": "moved",
                "dest": "/tmp/test.mp4",
                "confidence": "high",
            })


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
