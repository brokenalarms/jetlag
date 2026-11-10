"""
design/product.json holds the product facts the website states and the macOS
app has to honour. The free-file limit is checked on the app side by
LicenseStoreTests; this checks the minimum macOS the site advertises against
the deployment target the app is built for (macos/project.yml), so the site
never promises a macOS the app won't launch on.

Run: python3 -m unittest discover design/tests
"""
import json
import os
import re
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


class ProductFactsTests(unittest.TestCase):
    def test_minimum_macos_is_the_apps_deployment_target(self):
        with open(os.path.join(ROOT, "design", "product.json")) as f:
            product = json.load(f)
        with open(os.path.join(ROOT, "macos", "project.yml")) as f:
            project = f.read()
        match = re.search(r"deploymentTarget:\s*\n\s*macOS:\s*\"?([0-9.]+)\"?", project)
        self.assertIsNotNone(match, "no macOS deploymentTarget in macos/project.yml")
        self.assertEqual(product["minimumMacOS"], match.group(1))


if __name__ == "__main__":
    unittest.main()
