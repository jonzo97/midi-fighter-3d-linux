"""The printable cheat sheet must match the config it is generated from."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from macro.config import load_config  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "macro", "config.toml")


class TestCheatSheet(unittest.TestCase):
    def test_committed_cheat_sheet_matches_config(self):
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        from cheatsheet import render
        with open(os.path.join(ROOT, "docs", "CHEATSHEET.md")) as fh:
            committed = fh.read()
        self.assertEqual(committed, render(load_config(CONFIG)),
                         "run: python tools/cheatsheet.py --write")


if __name__ == "__main__":
    unittest.main()
