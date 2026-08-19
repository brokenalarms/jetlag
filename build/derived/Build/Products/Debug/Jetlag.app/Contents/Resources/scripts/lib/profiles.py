"""Resolve the media-profiles.yaml path — single source of truth for every script.

JETLAG_PROFILES_FILE overrides the default repo-level file. Tests point it at a
temp copy so suites can run in parallel without mutating shared repo state; it
also inherits into spawned script subprocesses.
"""
import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.parent


def resolve_profiles_file() -> Path:
    override = os.environ.get("JETLAG_PROFILES_FILE")
    if override:
        return Path(override)
    for name in ("media-profiles.yaml", "media-profiles.yml"):
        candidate = SCRIPT_DIR / name
        if candidate.exists():
            return candidate
    return SCRIPT_DIR / "media-profiles.yaml"
