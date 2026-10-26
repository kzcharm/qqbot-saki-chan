"""Exercise the real handler without loading NoneBot's plugin tree."""
import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Finished(Exception):
    pass


class TestModeHandler(unittest.TestCase):
    def setUp(self):
        source = ast.parse((ROOT / "src/plugins/gokz/core/kreedz.py").read_text())
        formatter = next(node for node in source.body if isinstance(node, ast.FunctionDef) and node.name == "format_kzmode")
        namespace = {}
        exec(compile(ast.Module(body=[formatter], type_ignores=[]), "kreedz.py", "exec"), namespace)
        self.user = SimpleNamespace(mode="kz_simple")
        self.commits = 0
        test = self

        class Session:
            def __init__(self, engine):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def get(self, *args):
                return test.user

            def add(self, user):
                pass

            def commit(self):
                test.commits += 1

            def refresh(self, user):
                pass

        async def finish(message):
            raise Finished(message)

        tree = ast.parse((ROOT / "src/plugins/gokz/plugins/general.py").read_text())
        handler = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "update_mode")
        handler.decorator_list = []
        namespace.update(Session=Session, engine=None, User=object, MessageEvent=object, Message=object,
                         CommandArg=lambda: None, mode=SimpleNamespace(finish=finish),
                         mode_selection_message=lambda mode: mode, binding_help_message=lambda: "bind first")
        exec(compile(ast.Module(body=[handler], type_ignores=[]), "general.py", "exec"), namespace)
        self.handler = namespace["update_mode"]

    def call(self, value):
        with self.assertRaises(Finished) as result:
            asyncio.run(self.handler(SimpleNamespace(get_user_id=lambda: "qid"),
                                     SimpleNamespace(extract_plain_text=lambda: value)))
        return result.exception.args[0]

    def test_picker_uses_saved_gokz_mode(self):
        self.assertEqual(self.call(""), "SKZ")
        self.assertEqual(self.commits, 0)

    def test_each_supported_mode_is_saved(self):
        for mode in ("ovr", "kzt", "skz", "vnl"):
            with self.subTest(mode=mode):
                self.assertEqual(self.call(mode), mode.upper())
                self.assertEqual(self.user.mode, mode.upper())
        self.assertEqual(self.commits, 4)

    def test_removed_mode_syntax_is_rejected_without_updates(self):
        for value in ("gokz kzt", "cs2kz vanilla", "classic", "ckz"):
            with self.subTest(value=value):
                self.assertEqual(self.call(value), "模式格式不正确")
                self.assertEqual(self.user.mode, "kz_simple")
        self.assertEqual(self.commits, 0)

    def test_unbound_user_receives_binding_help(self):
        self.user = None
        self.assertEqual(self.call("kzt"), "bind first")
        self.assertEqual(self.commits, 0)
