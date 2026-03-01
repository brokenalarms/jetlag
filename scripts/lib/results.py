"""Shared result serialisation for pipeline scripts.

Each script returns a dataclass from its core function. During the
subprocess era (before module-call migration), main() serialises the
result to @@key=value lines so media-pipeline.py can parse them.

emit_result() is the shared helper for that serialisation. It will be
deleted when the pipeline switches to direct module calls (step 3).
"""

import dataclasses


def emit_result(result) -> None:
    """Serialise a dataclass to @@key=value lines on stdout.

    - list fields are comma-joined
    - None fields are skipped (used for conditionally-present keys)
    - bool fields emit lowercase true/false
    """
    for field in dataclasses.fields(result):
        value = getattr(result, field.name)
        if value is None:
            continue
        if isinstance(value, list):
            value = ",".join(str(v) for v in value)
        elif isinstance(value, bool):
            value = str(value).lower()
        print(f"@@{field.name}={value}")
