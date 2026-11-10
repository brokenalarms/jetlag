"""
lib/profiles.py is the one place media-profiles.yaml is read; the pipeline and
generate-gyroflow both load through it instead of each parsing the YAML. These
tests pin what callers get back and how a missing file or profile is reported.
"""

import pytest

from lib.profiles import ProfileNotFound, ProfilesFileMissing, load_config, load_profile

PROFILES = """
gyroflow:
  preset: {stabilization: {max_zoom: 110.0}}
profiles:
  gopro:
    file_extensions: [.mp4]
    exif: {make: GoPro, model: HERO12 Black}
  sony:
    file_extensions: [.arw]
"""


@pytest.fixture
def profiles_file(tmp_path, monkeypatch):
    path = tmp_path / "media-profiles.yaml"
    path.write_text(PROFILES)
    monkeypatch.setenv("JETLAG_PROFILES_FILE", str(path))
    return path


def test_load_profile_returns_the_named_profile(profiles_file):
    assert load_profile("gopro")["exif"] == {"make": "GoPro", "model": "HERO12 Black"}


def test_load_config_carries_top_level_sections(profiles_file):
    assert load_config()["gyroflow"]["preset"] == {"stabilization": {"max_zoom": 110.0}}


def test_missing_profile_names_the_ones_that_exist(profiles_file):
    with pytest.raises(ProfileNotFound) as not_found:
        load_profile("canon")
    assert not_found.value.available == ["gopro", "sony"]


def test_missing_file_names_the_path(tmp_path, monkeypatch):
    missing = tmp_path / "nowhere.yaml"
    monkeypatch.setenv("JETLAG_PROFILES_FILE", str(missing))
    with pytest.raises(ProfilesFileMissing) as error:
        load_config()
    assert error.value.path == missing
