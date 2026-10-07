"""Verify the installed distribution exposes the documented module layout."""

import unittest
from importlib import import_module
from importlib.metadata import version


class PackageLayoutTests(unittest.TestCase):
    def test_distribution_metadata(self):
        self.assertEqual(version("tori-taurus"), "0.1.0")

    def test_documented_modules_are_importable(self):
        modules = (
            "market_data", "scanner", "catalysts", "indicators", "setups",
            "scoring", "risk", "behavior", "journal", "backtesting",
        )
        for name in modules:
            with self.subTest(module=name):
                module = import_module(f"tori_taurus.{name}")
                self.assertTrue(module.__doc__)


if __name__ == "__main__":
    unittest.main()
