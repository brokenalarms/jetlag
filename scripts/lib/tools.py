import os
import shutil


def resolve(name: str) -> str:
    env_key = f"JETLAG_{name.upper()}"
    path = os.environ.get(env_key)
    if path:
        return path
    path = shutil.which(name)
    if path:
        return path
    raise FileNotFoundError(
        f"{name} not found. Install via: brew install {name}"
    )
