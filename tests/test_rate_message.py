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


class TestRateMessage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for name in ("src", "src.plugins", "src.plugins.gokz", "src.plugins.gokz.core"):
            sys.modules.setdefault(name, types.ModuleType(name))
        load_module("src.plugins.gokz.core.keyboard", ROOT / "src/plugins/gokz/core/keyboard.py")
        cls.rate_message = load_module(
            "src.plugins.gokz.core.rate_message", ROOT / "src/plugins/gokz/core/rate_message.py"
        )

    def test_rate_picker_has_star_buttons_and_a_comment_action(self):
        message = self.rate_message.rate_selection_message("lionheart")

        self.assertEqual([segment.type for segment in message], ["markdown", "keyboard"])
        self.assertIn("**lionheart**", message[0].data["markdown"].content)
        rows = message[1].data["keyboard"].content.rows
        buttons = rows[0].buttons
        self.assertEqual([button.render_data.label for button in buttons], ["1⭐", "2⭐", "3⭐", "4⭐", "5⭐"])
        self.assertEqual([button.action.data for button in buttons], [
            "/rate lionheart 1", "/rate lionheart 2", "/rate lionheart 3",
            "/rate lionheart 4", "/rate lionheart 5",
        ])
        self.assertTrue(all(button.action.enter for button in buttons))
        comment_button = rows[1].buttons[0]
        self.assertEqual(comment_button.render_data.label, "写评论")
        self.assertEqual(comment_button.action.data, "/comment lionheart ")
        self.assertFalse(comment_button.action.enter)

    def test_rate_picker_highlights_only_the_current_rating(self):
        message = self.rate_message.rate_selection_message("lionheart", current_rating=3)

        buttons = message[1].data["keyboard"].content.rows[0].buttons
        self.assertEqual([button.render_data.style for button in buttons], [0, 0, 1, 0, 0])
