"""media-profiles.yaml: where it is and what it holds — the one place it is read.

JETLAG_PROFILES_FILE overrides the default repo-level file. Tests point it at a
temp copy so suites can run in parallel without mutating shared repo state; it
also inherits into spawned script subprocesses.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml

SCRIPT_DIR = Path(__file__).parent.parent


class ProfilesFileMissing(FileNotFoundError):
    """No profiles file exists at the resolved path."""

    def __init__(self, path: Path):
        super().__init__(f"Profiles file not found: {path}")
        self.path = path


class ProfileNotFound(LookupError):
    """The profiles file has no profile by that name."""

    def __init__(self, name: str, available: list[str]):
        super().__init__(f"Profile '{name}' not found")
        self.name = name
        self.available = available


def resolve_profiles_file() -> Path:
    override = os.environ.get("JETLAG_PROFILES_FILE")
    if override:
        return Path(override)
    for name in ("media-profiles.yaml", "media-profiles.yml"):
        candidate = SCRIPT_DIR / name
        if candidate.exists():
            return candidate
    return SCRIPT_DIR / "media-profiles.yaml"


def load_config() -> dict:
    """The whole profiles file: its profiles and top-level sections such as gyroflow.

    Raises ProfilesFileMissing when there is no file to read.
    """
    path = resolve_profiles_file()
    if not path.exists():
        raise ProfilesFileMissing(path)
    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_profile(name: str, config: Optional[dict] = None) -> dict:
    """The profile called name, from config or else from the profiles file.

    Raises ProfileNotFound (naming the profiles that do exist) when there is none,
    and ProfilesFileMissing when the file has to be read and is not there.
    """
    profiles = (config if config is not None else load_config()).get("profiles", {})
    if name not in profiles:
        raise ProfileNotFound(name, list(profiles))
    return profiles[name]
