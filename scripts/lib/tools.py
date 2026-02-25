import os
from pathlib import Path

# scripts/tools/ — vendored copies bundled with the app
_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"


def resolve(name: str) -> str:
    """Resolve a bundled tool by name.

    1. JETLAG_<NAME> env var (set by the macOS app pointing into the bundle)
    2. Vendored copy at scripts/tools/<name>
    """
    env_key = f"JETLAG_{name.upper()}"
    path = os.environ.get(env_key)
    if path:
        return path

    vendored = _TOOLS_DIR / name
    if vendored.is_file():
        return str(vendored)

    raise FileNotFoundError(f"{name} not found")
