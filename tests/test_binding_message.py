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


class TestBindingMessage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for name in ("src", "src.plugins", "src.plugins.gokz", "src.plugins.gokz.core"):
            sys.modules.setdefault(name, types.ModuleType(name))
        load_module("src.plugins.gokz.core.keyboard", ROOT / "src/plugins/gokz/core/keyboard.py")
        cls.binding_message = load_module(
            "src.plugins.gokz.core.binding_message", ROOT / "src/plugins/gokz/core/binding_message.py"
        )

    def test_binding_help_message_contains_instructions_and_actions(self):
        message = self.binding_message.binding_help_message()

        self.assertEqual([segment.type for segment in message], ["markdown", "keyboard"])
        content = message[0].data["markdown"].content
        self.assertIn(self.binding_message.BINDING_CODE_URL, content)
        self.assertIn("/bind KZTOP...", content)
        self.assertIn("5 分钟", content)
        self.assertIn("区分大小写", content)

        buttons = message[1].data["keyboard"].content.rows[0].buttons
        self.assertEqual(buttons[0].render_data.label, "打开绑定页面")
        self.assertEqual(buttons[0].action.type, 0)
        self.assertEqual(buttons[0].action.data, self.binding_message.BINDING_CODE_URL)
        self.assertEqual(buttons[1].render_data.label, "输入绑定命令")
        self.assertEqual(buttons[1].action.type, 2)
        self.assertEqual(buttons[1].action.data, "/bind ")
        self.assertFalse(buttons[1].action.enter)


if __name__ == "__main__":
    unittest.main()
