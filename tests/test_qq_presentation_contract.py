"""Freeze the original QQ presentation separately from Discord styling."""

import ast
import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class QQPresentationContractTests(unittest.TestCase):
    def test_original_qq_response_definitions_are_preserved(self):
        contract = json.loads(
            (ROOT / "tests/fixtures/qq_presentation_contract.json").read_text()
        )
        for filename, expected in contract["files"].items():
            with self.subTest(filename=filename):
                tree = ast.parse((ROOT / filename).read_text())
                # Adapter registration/import plumbing and the connect guard do
                # not affect message contents, keyboard actions, or panel rules.
                tree.body = [
                    node
                    for node in tree.body
                    if not isinstance(node, (ast.Import, ast.ImportFrom))
                    and not (
                        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and node.name == "_sync_panels_on_connect"
                    )
                ]
                actual = hashlib.sha256(
                    ast.dump(tree, include_attributes=False).encode()
                ).hexdigest()
                self.assertEqual(
                    actual,
                    expected,
                    "QQ presentation changed from the pre-refactor baseline",
                )
