"""
The exiftool client is the single metadata seam (lib/exiftool.py). These tests
cover the two things callers rely on it for beyond reading and writing: it owns
the per-file metadata cache and drops a file's entry whenever it writes that file,
and it can be constructed around any binary, so a stand-in needs no environment
variable set before import.
"""

import contextlib
import stat
from pathlib import Path

from conftest import create_test_video
from lib.exiftool import ExifTool, MetadataWriteRefused, exiftool
from lib.timestamp_source import read_exif_data


class TestWritesDropTheCachedRead:
    """A read after a write must see the write. Before the client owned the cache,
    each writer had to remember to clear it, and one that forgot handed later
    steps the pre-write values."""

    def test_read_after_write_sees_the_written_value(self, tmp_path):
        video = tmp_path / "clip.mp4"
        create_test_video(video)
        before = read_exif_data(str(video))
        assert "Make" not in before, f"Actual: {before.get('Make')!r}, Expected: no Make yet"

        exiftool.write_tags(str(video), ["-Make=TestMake"])

        after = read_exif_data(str(video))
        assert after.get("Make") == "TestMake", \
            f"Actual: Make={after.get('Make')!r} after the write, Expected: 'TestMake'"

    def test_a_refused_write_also_drops_the_cached_read(self, tmp_path):
        """A refusal may still have changed the file, so the cache cannot vouch for it."""
        video = tmp_path / "clip.mp4"
        create_test_video(video)
        read_exif_data(str(video))
        assert str(video) in exiftool.cache

        with contextlib.suppress(MetadataWriteRefused):
            exiftool.write_tags(str(video), ["-QuickTime:CreateDate=not a date"])

        assert str(video) not in exiftool.cache, \
            "Actual: the pre-write read is still cached, Expected: dropped by the write"


def test_client_runs_the_binary_it_is_given(tmp_path):
    """ExifTool(binary=...) starts that binary, whatever JETLAG_EXIFTOOL said at
    import time, so a test can hand a fake straight to a client."""
    fake = tmp_path / "fake-exiftool"
    started = tmp_path / "started"
    fake.write_text(f'''#!/usr/bin/env python3
import sys
open({str(started)!r}, "w").write(" ".join(sys.argv[1:]))
for line in sys.stdin:
    line = line.strip()
    if line.startswith("-execute"):
        print("{{ready" + line[len("-execute"):] + "}}", flush=True)
    if line == "False":
        break
''')
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)

    with ExifTool(binary=str(fake)) as client:
        client.execute("-ver")

    assert started.exists(), "Actual: the fake was never started, Expected: the client ran it"
    assert "-stay_open" in Path(started).read_text()
