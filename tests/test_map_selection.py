import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class TestMapSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for name in ("src", "src.plugins", "src.plugins.gokz", "src.plugins.gokz.core"):
            sys.modules.setdefault(name, types.ModuleType(name))
        load_module("src.plugins.gokz.core.keyboard", ROOT / "src/plugins/gokz/core/keyboard.py")
        sys.modules["src.plugins.gokz.core.kreedz"] = types.SimpleNamespace(search_map=lambda _: [])
        cls.map_selection = load_module(
            "src.plugins.gokz.core.map_selection",
            ROOT / "src/plugins/gokz/core/map_selection.py",
        )

    def test_exact_match_bypasses_picker_case_insensitively(self):
        self.map_selection.search_map = lambda _: ["kz_Example", "kz_example2"]

        resolved, candidates = self.map_selection.resolve_map_name("KZ_EXAMPLE")

        self.assertEqual(resolved, "kz_Example")
        self.assertEqual(candidates, [])

    def test_single_and_missing_matches_do_not_create_picker(self):
        self.map_selection.search_map = lambda _: ["kz_only"]
        self.assertEqual(self.map_selection.resolve_map_name("only"), ("kz_only", []))

        self.map_selection.search_map = lambda _: []
        self.assertEqual(self.map_selection.resolve_map_name("missing"), (None, []))

    def test_unique_prefix_stripped_exact_match_bypasses_picker(self):
        self.map_selection.search_map = lambda _: ["vnl_sewer", "kz_skytower"]

        self.assertEqual(self.map_selection.resolve_map_name("sewer"), ("vnl_sewer", []))

    def test_fuzzy_match_uses_basename_and_locks_on_clear_leader(self):
        self.map_selection.search_map = lambda _: [
            "kz_lionheart",
            "kz_lionharder",
            "kz_dishonest",
            "kz_slide_concrete",
        ]

        self.assertEqual(self.map_selection.resolve_map_name("lionhert"), ("kz_lionheart", []))

    def test_multiple_prefix_stripped_exact_matches_are_the_only_choices(self):
        self.map_selection.search_map = lambda _: [
            "vnl_sewer",
            "kz_sewer",
            "kz_skytower",
        ]

        self.assertEqual(
            self.map_selection.resolve_map_name("sewer"),
            (None, ["vnl_sewer", "kz_sewer"]),
        )

    def test_ambiguous_match_is_limited_to_five_candidates(self):
        matches = [f"kz_map_{index}" for index in range(6)]
        self.map_selection.search_map = lambda _: matches

        resolved, candidates = self.map_selection.resolve_map_name("map")

        self.assertIsNone(resolved)
        self.assertEqual(candidates, matches[:5])

    def test_picker_uses_map_labels_and_direct_submit_actions(self):
        message = self.map_selection.map_selection_message(
            ["kz_alpha", "kz_beta", "kz_gamma", "kz_delta", "kz_epsilon"],
            lambda map_name: self.map_selection.map_command("rate", map_name, "5", "great map"),
            "12345",
        )

        self.assertEqual([segment.type for segment in message], ["markdown", "keyboard"])
        self.assertIn("请选择地图", message[0].data["markdown"].content)
        rows = message[1].data["keyboard"].content.rows
        self.assertEqual([len(row.buttons) for row in rows], [1, 1, 1, 1, 1])
        buttons = [button for row in rows for button in row.buttons]
        self.assertEqual(
            [button.render_data.label for button in buttons],
            ["kz_alpha", "kz_beta", "kz_gamma", "kz_delta", "kz_epsilon"],
        )
        self.assertEqual(buttons[0].action.data, "/rate kz_alpha 5 great map")
        self.assertTrue(all(button.action.enter and button.action.reply for button in buttons))
        self.assertTrue(all(button.action.permission.type == 0 for button in buttons))
        self.assertTrue(all(button.action.permission.specify_user_ids == ["12345"] for button in buttons))

    def test_map_command_preserves_query_arguments(self):
        command = self.map_selection.map_command(
            "pb", "kz_alpha", "-m", "kz_timer", "-s", "76561198000000000"
        )

        self.assertEqual(command, "/pb kz_alpha -m kz_timer -s 76561198000000000")


if __name__ == "__main__":
    unittest.main()
