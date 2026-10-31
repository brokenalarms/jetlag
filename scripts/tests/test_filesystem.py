"""Tests for lib/filesystem.py media discovery."""

import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.filesystem import find_media_files, iter_media_files


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "card").mkdir()
    clip = tmp_path / "card" / "clip.mp4"
    clip.write_bytes(b"")
    (tmp_path / "card" / "._clip.mp4").write_bytes(b"")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "secret.mp4").write_bytes(b"")
    (tmp_path / "Photos.photoslibrary" / "originals").mkdir(parents=True)
    (tmp_path / "Photos.photoslibrary" / "originals" / "inside.mp4").write_bytes(b"")
    return tmp_path, clip


def test_find_media_files_skips_sidecars_hidden_dirs_and_packages(tree):
    # A source scan lists only the camera's visible clips, never exFAT ._ files,
    # hidden folders, or the contents of a Photos library.
    root, clip = tree
    assert find_media_files(str(root), [".mp4"]) == [clip]


def test_find_media_files_matches_extension_case_insensitively(tmp_path):
    # Clips named .MP4 or .Mp4 are found whatever case the camera wrote.
    upper = tmp_path / "A.MP4"
    mixed = tmp_path / "b.Mp4"
    upper.write_bytes(b"")
    mixed.write_bytes(b"")
    assert find_media_files(str(tmp_path), [".mp4"]) == [upper, mixed]


def test_iter_media_files_is_lazy_generator(tree):
    # Callers can stop counting early because the walk yields lazily.
    root, clip = tree
    files = iter_media_files(str(root), [".mp4"])
    assert isinstance(files, types.GeneratorType)
    assert next(files) == clip
