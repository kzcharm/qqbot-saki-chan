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


class TestModeMessage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for name in ("src", "src.plugins", "src.plugins.gokz", "src.plugins.gokz.core"):
            sys.modules.setdefault(name, types.ModuleType(name))
        load_module("src.plugins.gokz.core.keyboard", ROOT / "src/plugins/gokz/core/keyboard.py")
        cls.mode_message = load_module(
            "src.plugins.gokz.core.mode_message", ROOT / "src/plugins/gokz/core/mode_message.py"
        )

    def test_mode_picker_contains_all_modes_and_direct_submit_buttons(self):
        message = self.mode_message.mode_selection_message("SKZ")

        self.assertEqual([segment.type for segment in message], ["markdown", "keyboard"])
        self.assertIn("当前模式：**SKZ**", message[0].data["markdown"].content)
        rows = message[1].data["keyboard"].content.rows
        self.assertEqual([len(row.buttons) for row in rows], [4])
        buttons = [button for row in rows for button in row.buttons]
        self.assertEqual(
            [button.action.data for button in buttons],
            ["/mode ovr", "/mode kzt", "/mode skz", "/mode vnl"],
        )
        self.assertTrue(all(button.action.enter for button in buttons))
        self.assertEqual(buttons[2].render_data.style, 1)
