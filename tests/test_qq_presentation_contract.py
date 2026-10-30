"""Freeze the original QQ presentation separately from Discord styling."""

import ast
import hashlib
import json
import subprocess
import sys
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

    def test_original_qq_view_helpers_are_preserved(self):
        contract = json.loads(
            (ROOT / "tests/fixtures/qq_presentation_contract.json").read_text()
        )
        for filename, functions in contract["functions"].items():
            nodes = {
                node.name: node
                for node in ast.parse((ROOT / filename).read_text()).body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            for name, expected in functions.items():
                with self.subTest(filename=filename, function=name):
                    self.assertEqual(
                        hashlib.sha256(
                            ast.dump(nodes[name], include_attributes=False).encode()
                        ).hexdigest(),
                        expected,
                    )


class QQPayloadTests(unittest.TestCase):
    def test_shared_features_preserve_original_qq_payloads(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "tests/scenarios/qq_payloads.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            completed.returncode, 0, completed.stdout[-6000:] + completed.stderr[-6000:]
        )

    def test_qq_views_do_not_query_or_mutate_feature_state(self):
        for name in ("general", "gokz_top", "kzglobal", "perfectworld", "api_status"):
            tree = ast.parse((ROOT / f"src/plugins/gokz/plugins/{name}.py").read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    function = node.func.id if isinstance(node.func, ast.Name) else ""
                    self.assertNotIn(
                        function,
                        {
                            "fetch_json",
                            "put_json",
                            "post_json",
                            "Session",
                            "fetch_personal_best",
                            "fetch_world_record",
                            "fetch_run_history",
                            "fetch_personal_bans",
                            "verify_binding_code",
                            "get_daily_maps",
                            "player_card_screenshot_async",
                        },
                        f"{name} owns feature logic instead of calling the shared executor",
                    )
