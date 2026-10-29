#!/usr/bin/env python3
"""
Report which camera shot the media in a folder (or a single file).

Samples up to --sample files per extension and prints one JSON line on stdout
for each extension and camera found:

    {"extension": ".arw", "type": "photo", "make": "SONY", "model": "ILCE-7M5", "files": 10}

make/model are omitted when the files do not record them. type is the kind of
media the extension holds, which is what separates a camera's photo profile from
its video one. A readable summary goes to stderr.
"""

import argparse
import importlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

_tag_mod = importlib.import_module("tag-media")

VIDEO_EXTENSIONS = [".mp4", ".mov"]
PHOTO_EXTENSIONS = [".arw", ".cr2", ".dng", ".jpeg", ".jpg", ".nef", ".png"]
DEFAULT_EXTENSIONS = PHOTO_EXTENSIONS + VIDEO_EXTENSIONS

# Folders macOS presents as a single file. Their contents are another app's data,
# not a camera's originals, and reading into a Photos library asks the user for
# Photos access they never meant to give.
PACKAGE_SUFFIXES = {".photoslibrary", ".app", ".bundle", ".fcpbundle", ".imovielibrary",
                    ".tvlibrary", ".lrlibrary", ".lrdata", ".cocatalog"}


def _is_walked(name: str) -> bool:
    return not name.startswith(".") and Path(name).suffix.lower() not in PACKAGE_SUFFIXES


def sample_files(root: Path, extensions: list[str], sample: int) -> dict[str, list[Path]]:
    """The first `sample` files of each extension under root, in path order.

    One walk of the tree, ending as soon as every extension has its sample: a
    source can be a whole drive. Hidden entries are skipped, which includes the
    ._ files exFAT cards gain beside each clip, as are packages.
    """
    wanted = set(extensions)
    by_extension: dict[str, list[Path]] = {}
    for directory, dirs, files in os.walk(root):
        dirs[:] = sorted((d for d in dirs if _is_walked(d)), key=str.lower)
        for name in sorted(files, key=str.lower):
            extension = Path(name).suffix.lower()
            if extension not in wanted or name.startswith("."):
                continue
            kept = by_extension.setdefault(extension, [])
            if len(kept) < sample:
                kept.append(Path(directory) / name)
        if len(by_extension) == len(wanted) and all(len(k) >= sample for k in by_extension.values()):
            break
    return by_extension


def probe(path: Path, extensions: list[str], sample: int) -> list[dict]:
    if path.is_file():
        by_extension = {path.suffix.lower(): [path]}
    else:
        by_extension = sample_files(path, extensions, sample)

    found = []
    for extension, files in sorted(by_extension.items()):
        cameras = Counter(_tag_mod.file_camera(str(f)) for f in files)
        for (make, model), count in cameras.most_common():
            entry = {"extension": extension,
                     "type": "photo" if extension in PHOTO_EXTENSIONS else "video",
                     "files": count}
            if make:
                entry["make"] = make
            if model:
                entry["model"] = model
            found.append(entry)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description="Report the camera that shot a folder's media")
    parser.add_argument("path", help="Folder (searched recursively) or a single media file")
    parser.add_argument("--extensions", nargs="+", default=DEFAULT_EXTENSIONS,
                        help="Extensions to look for in a folder")
    parser.add_argument("--sample", type=int, default=10,
                        help="Files read per extension (default 10)")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"ERROR: {path} does not exist", file=sys.stderr)
        return 1

    extensions = [e.lower() if e.startswith(".") else f".{e.lower()}" for e in args.extensions]
    for entry in probe(path, extensions, args.sample):
        print(json.dumps(entry), flush=True)
        camera = " ".join(v for v in (entry.get("make"), entry.get("model")) if v) or "no camera recorded"
        print(f"{entry['extension']}: {camera} ({entry['files']} sampled)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
