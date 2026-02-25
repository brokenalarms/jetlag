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
        with mock.patch.dict(os.environ, {"JETLAG_EXIFTOOL": fake_path}):
            assert resolve("exiftool") == fake_path

    def test_vendored_fallback(self):
        """When env var is not set, finds vendored copy in scripts/tools/."""
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("JETLAG_EXIFTOOL", None)
            result = resolve("exiftool")
            assert result.endswith("tools/exiftool")

    def test_raises_when_not_found(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("JETLAG_FAKE", None)
            with pytest.raises(FileNotFoundError, match="fake not found"):
                resolve("fake")

    def test_env_var_name_uppercased(self, tmp_path):
        fake_path = str(tmp_path / "my-tool")
        with mock.patch.dict(os.environ, {"JETLAG_MY-TOOL": fake_path}):
            assert resolve("my-tool") == fake_path
