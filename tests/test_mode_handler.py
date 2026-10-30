"""Isolate NoneBot's runtime from the older unit tests' module stubs."""

import subprocess
import sys
import unittest
from pathlib import Path


class ModeHandlerTests(unittest.TestCase):
    def test_qq_mode_uses_shared_preferences_and_original_presentation(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, str(root / "tests/scenarios/qq_mode.py")],
            cwd=root,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode, 0, result.stdout[-6000:] + result.stderr[-6000:]
        )
