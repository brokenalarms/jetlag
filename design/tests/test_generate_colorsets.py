"""
Tests for design/generate-colorsets.py.

The script keeps the macOS app's colour sets in step with design/tokens.json.
Its --check mode is the drift guard: it must pass when the colour sets were
written from the current tokens, and fail when a token changes without the
colour sets being regenerated (or a colour set is missing).

Run: python3 -m unittest discover design/tests
"""
import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "generate-colorsets.py")


def load_script():
    spec = importlib.util.spec_from_file_location("generate_colorsets", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CheckModeTests(unittest.TestCase):
    def setUp(self):
        self.gen = load_script()
        self.tmp = tempfile.TemporaryDirectory()
        self.gen.XCASSETS_PATH = self.tmp.name
        with open(self.gen.TOKENS_PATH) as f:
            self.colors = json.load(f)["colors"]
        with contextlib.redirect_stdout(io.StringIO()):
            self.gen.write(self.colors)

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, colors):
        with contextlib.redirect_stdout(io.StringIO()):
            return self.gen.check(colors)

    # Freshly written colour sets are in step with the tokens they came from.
    def test_check_passes_after_write(self):
        self.assertEqual(self.check(self.colors), 0)

    # A token edited without regenerating is reported as drift for that colour set only.
    def test_check_reports_changed_token(self):
        changed = dict(self.colors, **{"neon-pink": "#ff0000"})
        self.assertEqual(self.check(changed), 1)

    # A deleted colour set counts as drift rather than crashing the check.
    def test_check_reports_missing_colorset(self):
        os.remove(self.gen.contents_path("NeonCyan"))
        self.assertEqual(self.check(self.colors), 1)

    # Every colour set the app reads by name is generated from a token.
    def test_map_covers_tokens(self):
        for token in self.gen.COLORSET_MAP:
            self.assertIn(token, self.colors)


if __name__ == "__main__":
    unittest.main()
