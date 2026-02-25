import os
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.tools import resolve


class TestResolve:
    def test_env_var_takes_precedence(self, tmp_path):
        fake_path = str(tmp_path / "custom-exiftool")
        Path(fake_path).touch()
        with mock.patch.dict(os.environ, {"JETLAG_EXIFTOOL": fake_path}):
            assert resolve("exiftool") == fake_path

    def test_falls_back_to_which(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("JETLAG_EXIFTOOL", None)
            with mock.patch("shutil.which", return_value="/usr/local/bin/exiftool"):
                assert resolve("exiftool") == "/usr/local/bin/exiftool"

    def test_raises_when_not_found(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("JETLAG_FAKE", None)
            with mock.patch("shutil.which", return_value=None):
                with pytest.raises(FileNotFoundError, match="^fake not found$"):
                    resolve("fake")

    def test_env_var_name_uppercased(self, tmp_path):
        fake_path = str(tmp_path / "my-tool")
        Path(fake_path).touch()
        with mock.patch.dict(os.environ, {"JETLAG_MY-TOOL": fake_path}):
            assert resolve("my-tool") == fake_path

    def test_env_var_nonexistent_file_falls_through(self, tmp_path):
        """Env var pointing to missing file should fall through to which()."""
        fake_path = str(tmp_path / "nonexistent-exiftool")
        with mock.patch.dict(os.environ, {"JETLAG_EXIFTOOL": fake_path}):
            with mock.patch("shutil.which", return_value="/usr/local/bin/exiftool"):
                assert resolve("exiftool") == "/usr/local/bin/exiftool"
