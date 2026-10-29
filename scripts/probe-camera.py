#!/usr/bin/env python3
"""
Report which camera shot the media in a folder (or a single file).

Samples up to --sample files per extension and prints one JSON line on stdout
for each extension and camera found:

    {"extension": ".arw", "type": "photo", "folder": "/Volumes/Untitled/DCIM",
     "make": "SONY", "model": "ILCE-7M5", "files": 10}

make/model are omitted when the files do not record them. type is the kind of
media the extension holds, which is what separates a camera's photo profile from
its video one. folder is the top-level folder under the probed path holding
those files (DCIM, PRIVATE, ...): the source a profile for them reads. A
readable summary goes to stderr.
"""

import argparse
import importlib
import json
import sys
from collections import Counter
from pathlib import Path

from lib.filesystem import find_media_files

_tag_mod = importlib.import_module("tag-media")

# The types whose camera tag-media can read; any other file would be reported as
# recording no camera when it may well record one.
VIDEO_EXTENSIONS = [".mp4", ".mov"]
PHOTO_EXTENSIONS = sorted(set(_tag_mod.CAMERA_EXIF_EXTENSIONS) - set(VIDEO_EXTENSIONS))
DEFAULT_EXTENSIONS = PHOTO_EXTENSIONS + VIDEO_EXTENSIONS


def top_folder(root: Path, file: Path) -> str:
    """The folder directly under root that holds file; root itself for a file
    at its top level, or when root is the file."""
    if root.is_file():
        return str(file.parent)
    relative = file.relative_to(root)
    return str(root / relative.parts[0]) if len(relative.parts) > 1 else str(root)


def probe(path: Path, extensions: list[str], sample: int) -> list[dict]:
    if path.is_file():
        by_extension = {path.suffix.lower(): [path]}
    else:
        by_extension: dict[str, list[Path]] = {}
        for file in find_media_files(str(path), extensions):
            by_extension.setdefault(file.suffix.lower(), []).append(file)

    found = []
    for extension, files in sorted(by_extension.items()):
        sampled = files[:sample]
        cameras = Counter((_tag_mod.file_camera(str(f)), top_folder(path, f)) for f in sampled)
        for ((make, model), folder), count in cameras.most_common():
            entry = {"extension": extension,
                     "type": "photo" if extension in PHOTO_EXTENSIONS else "video",
                     "folder": folder,
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
