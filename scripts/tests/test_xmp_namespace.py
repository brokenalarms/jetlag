#!/usr/bin/env python3
"""
Provenance lives in jetlag's own XMP namespace, and exiftool silently skips a tag it
has no definition for. If either metadata backend starts exiftool without the jetlag
config, every provenance write is dropped with no error. Each backend writes a
XMP-jetlag property here and a plain exiftool, with no config, must read it back.
"""

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from conftest import create_test_video
from lib.exiftool import ExifTool
from lib.metadata import _SwiftBackend


def _read_without_config(path: Path) -> str:
    return subprocess.run(
        ["exiftool", "-s3", "-XMP-jetlag:OriginalCreateDate", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


@pytest.fixture(params=["python", "swift"])
def backend(request, metadata_client):
    if request.param == "python":
        return metadata_client(ExifTool())
    binary = request.getfixturevalue("jetlag_metadata_binary")
    return metadata_client(_SwiftBackend(str(binary)))


def test_backend_writes_jetlag_namespace(backend, tmp_path):
    video = tmp_path / "VID_20250618_072521.mp4"
    create_test_video(video)

    assert backend.write_tags(str(video), ["-XMP-jetlag:OriginalCreateDate=2025:06:17 23:25:21"])

    assert _read_without_config(video) == "2025:06:17 23:25:21"
