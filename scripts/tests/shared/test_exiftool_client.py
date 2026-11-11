"""
The exiftool client is the single metadata seam (lib/exiftool.py). These tests
cover what callers rely on it for beyond reading and writing: it owns the
per-file metadata cache and drops a file's entry whenever it writes that file;
it can be constructed around any binary, so a stand-in needs no environment
variable set before import; and a refusal names its real reason.
"""

from __future__ import annotations

import contextlib
import stat
from pathlib import Path

import pytest

from helpers.media import create_insv_with_corrupted_trailer, create_test_video
from lib.exiftool import ExifTool, Insta360TrailerCorrupted, MetadataWriteRefused, exiftool
from lib.timestamps.sources import read_exif_data


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


def _x6_like_exiftool(path: Path, with_m_error: str | None) -> Path:
    """A -stay_open stand-in that refuses a write the way exiftool refuses an
    Insta360 X6 clip: a minor error first, and with -m, with_m_error (None: the
    -m write succeeds). The args of every command are logged, one per line."""
    log = path.with_suffix(".log")
    path.write_text(f'''#!/usr/bin/env python3
import sys
args = []
for raw in sys.stdin:
    line = raw.strip()
    if line == "False":
        break
    if not line.startswith("-execute"):
        args.append(line)
        continue
    n = line[len("-execute"):]
    marker = args[args.index("-echo4") + 1]
    target = args[-1]
    with open({str(log)!r}, "a") as f:
        f.write(" ".join(args) + "\\n")
    if "-m" not in args:
        sys.stderr.write("Error: [minor] Terminator found in Meta with 41 bytes remaining - " + target + "\\n")
        sys.stdout.write("    0 image files updated\\n    1 files weren't updated due to errors\\n")
    elif {with_m_error!r} is None:
        sys.stdout.write("    1 image files updated\\n")
    else:
        sys.stderr.write("Warning: Terminator found in Meta with 41 bytes remaining - " + target + "\\n")
        sys.stderr.write("Error: " + {with_m_error!r} + " - " + target + "\\n")
        sys.stdout.write("    0 image files updated\\n    1 files weren't updated due to errors\\n")
    sys.stderr.write(marker + "\\n")
    sys.stderr.flush()
    sys.stdout.write("{{ready" + n + "}}\\n")
    sys.stdout.flush()
    args = []
''')
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return log


class TestAMinorRefusalIsRetriedWithM:
    """exiftool stops a write at its first error, and some errors are minor: -m
    lets the write past them. The Insta360 X6 writes an empty terminator in its
    meta atom, a minor error that hides the real reason its clips cannot be
    written, a corrupted trailer, which only -m reveals. So a refusal made of
    minor errors alone is retried once with -m, and the caller learns the real
    reason or gets the write."""

    def test_the_x6_refusal_names_its_corrupted_trailer(self, tmp_path):
        """Actual: what the write raises, and the commands it sent
        Expected: Insta360TrailerCorrupted after a second write with -m"""
        log = _x6_like_exiftool(tmp_path / "exiftool", "Corrupted Insta360 trailer")

        with ExifTool(binary=str(tmp_path / "exiftool")) as client:
            with pytest.raises(Insta360TrailerCorrupted, match="Corrupted Insta360 trailer"):
                client.write_tags(str(tmp_path / "clip.insv"), ["-Keys:CreationDate=2026:10:06 15:28:02+08:00"])

        writes = log.read_text().splitlines()
        assert len(writes) == 2 and " -m " not in writes[0] and " -m " in writes[1], \
            f"Actual: {writes}, Expected: the write, then the same write with -m"

    def test_a_refusal_of_minor_errors_alone_is_written_with_m(self, tmp_path):
        _x6_like_exiftool(tmp_path / "exiftool", None)

        with ExifTool(binary=str(tmp_path / "exiftool")) as client:
            assert client.write_tags(str(tmp_path / "clip.mp4"), ["-Make=TestMake"]) is True

    def test_another_refusal_after_m_stays_a_plain_refusal(self, tmp_path):
        _x6_like_exiftool(tmp_path / "exiftool", "Not a valid MP4")

        with ExifTool(binary=str(tmp_path / "exiftool")) as client:
            with pytest.raises(MetadataWriteRefused, match="Not a valid MP4") as refused:
                client.write_tags(str(tmp_path / "clip.mp4"), ["-Make=TestMake"])
        assert not isinstance(refused.value, Insta360TrailerCorrupted)

    def test_real_exiftool_refuses_a_corrupted_trailer_as_such(self, tmp_path):
        """The real binary on a clip whose trailer overlaps its last atom, with an
        empty record table as the X6 writes it."""
        clip = tmp_path / "clip.insv"
        create_insv_with_corrupted_trailer(clip)

        with pytest.raises(Insta360TrailerCorrupted):
            exiftool.write_tags(str(clip), ["-Keys:CreationDate=2026:10:06 15:28:02+08:00"])
