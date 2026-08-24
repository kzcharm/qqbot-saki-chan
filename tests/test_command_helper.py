import unittest
import importlib.util
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class TestCommandHelper(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for name in ("src", "src.plugins", "src.plugins.gokz", "src.plugins.gokz.core", "src.plugins.gokz.db"):
            sys.modules.setdefault(name, types.ModuleType(name))
        load_module("src.plugins.gokz.core.config", ROOT / "src/plugins/gokz/core/config.py")
        load_module("src.plugins.gokz.core.kreedz", ROOT / "src/plugins/gokz/core/kreedz.py")
        sys.modules["src.plugins.gokz.db.db"] = types.SimpleNamespace(engine=None)
        sys.modules["src.plugins.gokz.db.models"] = types.SimpleNamespace(User=object)
        sys.modules["src.plugins.gokz.core.steam_user"] = types.SimpleNamespace(convert_steamid=lambda value, _: value)
        sys.modules["src.plugins.gokz.core.game"] = types.SimpleNamespace(format_cs2kz_mode=lambda mode: mode)
        cls.binding_help_message = object()
        sys.modules["src.plugins.gokz.core.binding_message"] = types.SimpleNamespace(
            binding_help_message=lambda: cls.binding_help_message
        )
        cls.command_helper = load_module(
            "src.plugins.gokz.core.command_helper", ROOT / "src/plugins/gokz/core/command_helper.py"
        )
        cls.parse_args = staticmethod(cls.command_helper.parse_args)

    def test_map_name_is_not_treated_as_mode(self):
        parsed = self.parse_args("innit")

        self.assertIsNone(parsed["mode"])
        self.assertEqual(parsed["args"], ("innit",))

    def test_mode_can_appear_before_or_after_map(self):
        for text, mode in (("k innit", "k"), ("innit k", "k"), ("KZT innit", "kzt"), ("innit kz_timer", "kz_timer")):
            with self.subTest(text=text):
                parsed = self.parse_args(text)
                self.assertEqual(parsed["mode"].lower(), mode)
                self.assertEqual(parsed["args"], ("innit",))

    def test_explicit_invalid_mode_is_preserved_for_validation(self):
        parsed = self.parse_args("innit -m invalid")

        self.assertEqual(parsed["mode"], "invalid")
        self.assertEqual(parsed["args"], ("innit",))

    def test_unbound_user_receives_shared_binding_help_message(self):
        class NoUserSession:
            def __init__(self, _engine):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def get(self, *_args):
                return None

        class Event:
            def get_user_id(self):
                return "123"

        class Args:
            def extract_plain_text(self):
                return ""

        original_session = self.command_helper.Session
        self.command_helper.Session = NoUserSession
        try:
            command_data = self.command_helper.CommandData(Event(), Args())
        finally:
            self.command_helper.Session = original_session

        self.assertIs(command_data.error, self.binding_help_message)

    def test_argument_errors_remain_plain_text(self):
        class Event:
            def get_user_id(self):
                return "123"

        class Args:
            def extract_plain_text(self):
                return '"'

        command_data = self.command_helper.CommandData(Event(), Args())

        self.assertIsInstance(command_data.error, str)


if __name__ == "__main__":
    unittest.main()
