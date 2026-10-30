"""Run integration tests isolated from legacy tests' sys.modules stubs."""
import subprocess
import sys
import unittest
from pathlib import Path


class UnifiedApplicationTests(unittest.TestCase):
    def test_unified_application(self):
        root=Path(__file__).resolve().parents[1]
        completed=subprocess.run([sys.executable,str(root/'tests/scenarios/unified_application.py')],cwd=root,capture_output=True,text=True)
        self.assertEqual(completed.returncode,0,completed.stdout[-6000:]+completed.stderr[-6000:])
