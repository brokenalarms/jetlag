#!/usr/bin/env python3
"""
verify-card decides whether a card is safe to wipe: every file on it must be provably
on every backup location, and nothing may pass on a guess. These tests build a card
and its backup locations on disk, run the script, and read its verdicts.

What has to hold:
- a copy is found anywhere under a location's root, by its card name or by the card
  name its provenance records, since an import renames files and later regrouping
  moves them;
- a copy passes on equal total size (untouched) or equal data portion (a copy jetlag
  has written, whose metadata moved), and fails on anything else;
- a remote location is never read: a copy that cannot be judged from its listing, or
  from a local twin, is "unverifiable", never matched;
- the card is never written.

Every event is checked against verify-card-schema.yaml.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import create_test_photo, create_test_video
from pipeline_schema import load_schema, validate_event

SCRIPT_DIR = Path(__file__).parent.parent
VERIFY_CARD = SCRIPT_DIR / "verify-card.py"
SCHEMA = load_schema(SCRIPT_DIR / "verify-card-schema.yaml")

sys.path.insert(0, str(SCRIPT_DIR))
from lib.exiftool import exiftool  # noqa: E402

CLIP = "VID_20250619_042028_00_004.mp4"
RENAMED_CLIP = "VID_20250619_072028_00_004.mp4"


def run_verify(source: Path, locations: dict[str, str], *extra: str, env: dict | None = None) -> dict:
    args = [sys.executable, str(VERIFY_CARD), str(source),
            "--media-extensions", ".mp4", ".jpg", ".arw",
            "--companion-extensions", ".lrv", ".thm",
            "--ignore-paths", "MISC"]
    for name, root in locations.items():
        args += ["--location", f"{name}={root}"]
    result = subprocess.run(args + list(extra), capture_output=True, text=True, cwd=SCRIPT_DIR,
                            env={**os.environ, **(env or {})})
    assert result.returncode == 0, result.stderr
    events = [json.loads(line) for line in result.stdout.splitlines()]
    for event in events:
        validate_event(event, SCHEMA)
    return {
        "locations": {e["location"]: e for e in events if e["event"] == "verify_location"},
        "files": {e["file"]: e for e in events if e["event"] == "verify_file"},
        "results": {(e["file"], e["location"]): e for e in events if e["event"] == "verify_result"},
        "summary": next(e for e in events if e["event"] == "verify_summary"),
    }


def write_tags(path: Path, *tags: str):
    """Rewrite a copy as jetlag's import would: its metadata moves, its data does not."""
    assert exiftool.write_tags(str(path), list(tags))


def copy_to(card_file: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(card_file, dest)
    return dest


def outcome(report: dict, file: str, location: str) -> tuple:
    result = report["results"][(file, location)]
    return result["verdict"], result.get("basis"), result["copies"]


@pytest.fixture
def card(tmp_path):
    root = tmp_path / "card"
    clip = root / "DCIM" / CLIP
    create_test_video(clip)
    return root


class TestFindingCopies:
    """A copy is found wherever it sits under the root, by name or recorded name."""

    def test_untouched_copy_anywhere_under_the_root_matches_on_size(self, card, tmp_path):
        library = tmp_path / "T9"
        copy_to(card / "DCIM" / CLIP, library / "2025" / "Japan" / "2025-06-19" / CLIP)

        report = run_verify(card, {"T9": str(library)})

        assert outcome(report, f"DCIM/{CLIP}", "T9") == \
            ("matched", "size", [f"2025/Japan/2025-06-19/{CLIP}"])

    def test_renamed_written_copy_matches_by_recorded_name_and_data_portion(self, card, tmp_path):
        library = tmp_path / "T9"
        copy = copy_to(card / "DCIM" / CLIP, library / "2025" / RENAMED_CLIP)
        write_tags(copy, f"-XMP-xmpMM:PreservedFileName={CLIP}", "-Make=Insta360")
        assert copy.stat().st_size != (card / "DCIM" / CLIP).stat().st_size

        report = run_verify(card, {"T9": str(library)})

        assert outcome(report, f"DCIM/{CLIP}", "T9") == ("matched", "data", [f"2025/{RENAMED_CLIP}"])

    def test_legacy_logcomment_record_names_the_card_file(self, card, tmp_path):
        library = tmp_path / "T9"
        copy = copy_to(card / "DCIM" / CLIP, library / RENAMED_CLIP)
        write_tags(copy, f'-XMP-xmpDM:LogComment={{"version":1,"filename":"{CLIP}"}}')

        report = run_verify(card, {"T9": str(library)})

        assert outcome(report, f"DCIM/{CLIP}", "T9") == ("matched", "data", [RENAMED_CLIP])

    def test_copy_recording_another_card_name_is_not_this_files_copy(self, card, tmp_path):
        """Renaming can give a clip the name of a different card clip; its record, not
        its name, says which card file it is."""
        library = tmp_path / "T9"
        copy = copy_to(card / "DCIM" / CLIP, library / CLIP)
        write_tags(copy, f"-XMP-xmpMM:PreservedFileName={RENAMED_CLIP}")

        report = run_verify(card, {"T9": str(library)})

        assert outcome(report, f"DCIM/{CLIP}", "T9") == ("missing", None, [])

    def test_copy_in_a_sync_archive_is_not_backed_up(self, card, tmp_path):
        library = tmp_path / "NAS"
        copy_to(card / "DCIM" / CLIP, library / "#recycle" / CLIP)
        copy_to(card / "DCIM" / CLIP, library / ".stversions" / CLIP)

        report = run_verify(card, {"NAS": str(library)})

        assert outcome(report, f"DCIM/{CLIP}", "NAS") == ("missing", None, [])

    def test_two_copies_on_one_location_are_duplicates(self, card, tmp_path):
        library = tmp_path / "T9"
        copy_to(card / "DCIM" / CLIP, library / "a" / CLIP)
        copy_to(card / "DCIM" / CLIP, library / "b" / CLIP)

        report = run_verify(card, {"T9": str(library)})

        assert outcome(report, f"DCIM/{CLIP}", "T9") == ("duplicate", None, [f"a/{CLIP}", f"b/{CLIP}"])


class TestJudgingCopies:
    """Nothing passes on a guess: a copy must equal the card file in total size or data."""

    def test_truncated_copy_differs(self, card, tmp_path):
        library = tmp_path / "T9"
        copy = copy_to(card / "DCIM" / CLIP, library / CLIP)
        with open(copy, "r+b") as f:
            f.truncate(copy.stat().st_size - 100)

        report = run_verify(card, {"T9": str(library)})

        assert outcome(report, f"DCIM/{CLIP}", "T9") == ("data_differs", None, [CLIP])

    def test_written_photo_matches_on_its_data_portion(self, card, tmp_path):
        photo = card / "DCIM" / "IMG_0001.jpg"
        create_test_photo(photo)
        library = tmp_path / "T9"
        copy = copy_to(photo, library / "IMG_0001.jpg")
        write_tags(copy, "-XMP-xmpMM:PreservedFileName=IMG_0001.jpg", "-Make=Sony")
        assert copy.stat().st_size != photo.stat().st_size

        report = run_verify(card, {"T9": str(library)})

        assert outcome(report, "DCIM/IMG_0001.jpg", "T9") == ("matched", "data", ["IMG_0001.jpg"])

    def test_format_without_a_reader_is_unverifiable_when_sizes_differ(self, card, tmp_path):
        raw = card / "DCIM" / "DSC0001.arw"
        raw.write_bytes(b"II*\x00" + bytes(2000))
        library = tmp_path / "T9"
        library.mkdir()
        (library / "DSC0001.arw").write_bytes(b"II*\x00" + bytes(2100))

        report = run_verify(card, {"T9": str(library)})

        assert outcome(report, "DCIM/DSC0001.arw", "T9") == ("unverifiable", None, ["DSC0001.arw"])

    def test_every_enabled_location_is_judged_on_its_own(self, card, tmp_path):
        t9, nas = tmp_path / "T9", tmp_path / "NAS"
        copy_to(card / "DCIM" / CLIP, t9 / CLIP)
        nas.mkdir()

        report = run_verify(card, {"T9": str(t9), "NAS": str(nas)})

        verdicts = {loc: outcome(report, f"DCIM/{CLIP}", loc)[0] for loc in ("T9", "NAS")}
        assert verdicts == {"T9": "matched", "NAS": "missing"}
        assert (report["summary"]["on_every_location"], report["summary"]["need_attention"]) == (0, 1)

    def test_unreachable_location_passes_nothing(self, card, tmp_path):
        report = run_verify(card, {"T9": str(tmp_path / "unplugged")})

        assert report["locations"]["T9"]["reachable"] is False
        assert outcome(report, f"DCIM/{CLIP}", "T9") == ("unreachable", None, [])


class TestWhatIsChecked:
    """The source is sorted by the lists the check is given; the rest is counted."""

    def test_ignored_hidden_and_other_files(self, card, tmp_path):
        (card / "MISC").mkdir()
        (card / "MISC" / CLIP).write_bytes(b"stub")
        (card / "DCIM" / f"._{CLIP}").write_bytes(b"x")
        (card / ".dcf_reserved_space").write_bytes(b"x")
        (card / "DCIM" / "camera.BIN").write_bytes(b"x")
        (card / "DCIM" / "VID_20250619_042028_00_004.lrv").write_bytes(b"x" * 10)
        library = tmp_path / "T9"
        copy_to(card / "DCIM" / CLIP, library / CLIP)

        report = run_verify(card, {"T9": str(library)})

        assert list(report["files"]) == [f"DCIM/{CLIP}"]
        assert (report["summary"]["not_checked"], report["summary"]["not_checked_kinds"]) == \
            (3, [".bin", ".lrv", "MISC/"])

    def test_companion_renamed_with_its_clip_is_found_beside_the_clips_copy(self, card, tmp_path):
        """An import renames a clip's companions with it, and they carry no record."""
        companion = card / "DCIM" / "VID_20250619_042028_00_004.lrv"
        companion.write_bytes(b"low-res" * 100)
        library = tmp_path / "T9"
        copy = copy_to(card / "DCIM" / CLIP, library / "g" / RENAMED_CLIP)
        write_tags(copy, f"-XMP-xmpMM:PreservedFileName={CLIP}")
        copy_to(companion, library / "g" / "VID_20250619_072028_00_004.lrv")

        report = run_verify(card, {"T9": str(library)}, "--include-companions")

        assert outcome(report, "DCIM/VID_20250619_042028_00_004.lrv", "T9") == \
            ("matched", "size", ["g/VID_20250619_072028_00_004.lrv"])

    def test_check_never_writes_the_card(self, card, tmp_path):
        library = tmp_path / "T9"
        copy_to(card / "DCIM" / CLIP, library / CLIP)
        clip = card / "DCIM" / CLIP
        before = (hashlib.sha256(clip.read_bytes()).hexdigest(), clip.stat().st_mtime_ns)

        run_verify(card, {"T9": str(library)})

        assert (hashlib.sha256(clip.read_bytes()).hexdigest(), clip.stat().st_mtime_ns) == before


class TestRemoteLocation:
    """A host:/path location is listed by rsync and never read over the network.

    A stand-in rsync drops the host and lists the path locally, so the listing is
    real rsync output.
    """

    @pytest.fixture
    def rsync_env(self, tmp_path):
        stub = tmp_path / "fake-rsync"
        stub.write_text(
            "#!/bin/bash\n"
            'args=()\nfor a in "$@"; do args+=("${a#nas:}"); done\n'
            'exec rsync "${args[@]}"\n'
        )
        stub.chmod(0o755)
        return {"JETLAG_RSYNC": str(stub)}

    def test_untouched_remote_copy_matches_on_its_listed_size(self, card, tmp_path, rsync_env):
        remote = tmp_path / "nas"
        copy_to(card / "DCIM" / CLIP, remote / "2025" / CLIP)

        report = run_verify(card, {"NAS": f"nas:{remote}"}, env=rsync_env)

        assert report["locations"]["NAS"]["remote"] is True
        assert outcome(report, f"DCIM/{CLIP}", "NAS") == ("matched", "size", [f"2025/{CLIP}"])

    def test_written_remote_copy_is_judged_from_its_local_twin(self, card, tmp_path, rsync_env):
        local, remote = tmp_path / "T9", tmp_path / "nas"
        copy = copy_to(card / "DCIM" / CLIP, local / "2025" / RENAMED_CLIP)
        write_tags(copy, f"-XMP-xmpMM:PreservedFileName={CLIP}")
        copy_to(copy, remote / "2025" / RENAMED_CLIP)

        report = run_verify(card, {"T9": str(local), "NAS": f"nas:{remote}"}, env=rsync_env)

        assert outcome(report, f"DCIM/{CLIP}", "NAS") == ("matched", "data", [f"2025/{RENAMED_CLIP}"])

    def test_written_remote_copy_without_a_twin_is_unverifiable(self, card, tmp_path, rsync_env):
        remote = tmp_path / "nas"
        copy = copy_to(card / "DCIM" / CLIP, remote / CLIP)
        write_tags(copy, f"-XMP-xmpMM:PreservedFileName={CLIP}")

        report = run_verify(card, {"NAS": f"nas:{remote}"}, env=rsync_env)

        assert outcome(report, f"DCIM/{CLIP}", "NAS") == ("unverifiable", None, [CLIP])
