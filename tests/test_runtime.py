import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location("bot_runtime", Path(__file__).resolve().parents[1] / "runtime.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RuntimeTests(unittest.TestCase):
    def test_adapter_modes(self):
        for names in ("qq", "discord", "qq,discord"):
            config = SimpleNamespace(qq_bots=[{}], discord_bots=[{}], bot_platforms=names)
            self.assertEqual(module.enabled_platforms(config), tuple(names.split(",")))

    def test_qq_only_compatibility(self):
        self.assertEqual(module.enabled_platforms(SimpleNamespace(qq_bots=[{}])), ("qq",))

    def test_missing_credentials_and_typo_fail(self):
        for names in ("discord", "q", ""):
            with self.assertRaises(ValueError):
                module.enabled_platforms(SimpleNamespace(qq_bots=[{}], bot_platforms=names))
