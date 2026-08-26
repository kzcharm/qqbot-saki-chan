import ast
import importlib.util
from types import SimpleNamespace
import unittest
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]


def load_pb_action_keyboard():
    """Load the keyboard builder without starting the complete plugin tree."""
    keyboard_spec = importlib.util.spec_from_file_location(
        "keyboard_under_test", ROOT / "src/plugins/gokz/core/keyboard.py"
    )
    assert keyboard_spec and keyboard_spec.loader
    keyboard_module = importlib.util.module_from_spec(keyboard_spec)
    keyboard_spec.loader.exec_module(keyboard_module)

    source = (ROOT / "src/plugins/gokz/plugins/kzglobal.py").read_text(encoding="utf-8")
    function = next(
        node for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name == "pb_action_keyboard"
    )
    namespace = {
        "CommandData": object,
        "Event": object,
        "KeyboardBuilder": keyboard_module.KeyboardBuilder,
        "format_kzmode": lambda mode, _: mode,
        "quote": quote,
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), "kzglobal.py", "exec"), namespace)
    return namespace["pb_action_keyboard"]


pb_action_keyboard = load_pb_action_keyboard()


class TestPbActionKeyboard(unittest.TestCase):
    def test_group_result_includes_self_record_action_for_any_viewer(self):
        event = SimpleNamespace(group_openid="group-1")
        command = SimpleNamespace(
            game="gokz",
            mode="kzt",
            steamid="sender-steamid",
            steamid2=None,
        )

        keyboard = pb_action_keyboard(event, command, "kz_surf_larry")
        rows = keyboard.data["keyboard"].content.rows
        first_button = rows[0].buttons[0]

        self.assertEqual(first_button.id, "pb_self")
        self.assertEqual(first_button.render_data.label, "查询我的记录")
        self.assertEqual(first_button.action.data, "/pb kz_surf_larry -m KZT")
        self.assertEqual([len(row.buttons) for row in rows], [2, 2, 2, 2])

    def test_private_query_does_not_include_self_record_action(self):
        event = SimpleNamespace()
        command = SimpleNamespace(
            game="gokz",
            mode="kzt",
            steamid="target-steamid",
            steamid2="sender-steamid",
        )

        keyboard = pb_action_keyboard(event, command, "kz_surf_larry")
        button_ids = [
            button.id
            for row in keyboard.data["keyboard"].content.rows
            for button in row.buttons
        ]

        self.assertNotIn("pb_self", button_ids)
