#!/usr/bin/env python3
"""
An Insta360 .insv/.insp records its camera Model only in a trailer that exiftool
parses under ExtractEmbedded. The camera check, tagging and probe-camera all read
the camera through read_exif_data, so each must see that Model — and only those
two suffixes pay for the embedded-data read.

The trailer is generated here (the layout ProcessInsta360 expects), so no device
footage is shipped.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from conftest import create_insta360_file

SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib import timestamp_source

spec = importlib.util.spec_from_file_location("tag_media", str(SCRIPT_DIR / "tag-media.py"))
tm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tm)


def test_insv_reports_the_model_its_trailer_records(tmp_path):
    """The camera check sees an .insv's Model, which only the trailer carries."""
    insv = create_insta360_file(tmp_path / "VID_0001.insv", "Insta360 X4")

    make, model = tm.file_camera(str(insv))

    assert model == "Insta360 X4", f"Actual: {model!r}, Expected: the trailer's Model"


def test_insv_with_another_profiles_camera_is_flagged(tmp_path):
    """A profile for a different camera is flagged against the .insv, and the
    profile's camera is not written over the Model the file records."""
    insv = create_insta360_file(tmp_path / "VID_0002.insv", "Insta360 X4")

    mismatch = tm.camera_mismatch(str(insv), None, "ILCE-7M5")
    fields = tm.camera_exif_fields(str(insv), None, "ILCE-7M5")

    assert mismatch == {"Model": "Insta360 X4"}, f"Actual: {mismatch}"
    assert "Model" not in fields, f"Actual: {fields}, Expected no Model to write"


def test_other_suffixes_are_read_without_embedded_data(tmp_path, monkeypatch):
    """-ee parses every timed-metadata track, so only .insv/.insp ask for it."""
    seen = {}

    def fake_read_tags(file_path, tags, extra_args=None):
        seen[Path(file_path).name] = extra_args
        return {}

    monkeypatch.setattr(timestamp_source.exiftool, "read_tags", fake_read_tags)
    timestamp_source._exif_cache.clear()

    for name in ("a.insv", "b.INSP", "c.mp4", "d.jpg"):
        timestamp_source.read_exif_data(str(tmp_path / name))

    assert seen == {"a.insv": ["-ee"], "b.INSP": ["-ee"], "c.mp4": None, "d.jpg": None}


def test_probe_camera_reports_an_insv_folder(tmp_path):
    """A folder probe finds .insv files and reports the camera in their trailer."""
    create_insta360_file(tmp_path / "VID_0003.insv", "Insta360 X4")

    result = subprocess.run([sys.executable, str(SCRIPT_DIR / "probe-camera.py"), str(tmp_path)],
                            capture_output=True, text=True, cwd=SCRIPT_DIR)
    found = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]

    assert found == [{"extension": ".insv", "type": "video", "files": 1, "model": "Insta360 X4"}], \
        f"Actual: {found}, stderr: {result.stderr}"
