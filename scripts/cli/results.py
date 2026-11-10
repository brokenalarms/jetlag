"""Shared result serialisation for the single-file scripts' command lines.

Each script's core function returns a dataclass. The pipeline calls those
functions in-process and reads the dataclass directly; a script run on its own
prints the same result as @@key=value lines through emit_result().
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
