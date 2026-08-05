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


class CS2KZTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for name in ("src", "src.plugins", "src.plugins.gokz", "src.plugins.gokz.core", "src.plugins.gokz.api"):
            sys.modules.setdefault(name, types.ModuleType(name))
        cls.game = load_module("src.plugins.gokz.core.game", ROOT / "src/plugins/gokz/core/game.py")
        sys.modules["src.plugins.gokz.core.steam_user"] = types.SimpleNamespace(convert_steamid=lambda value, _: value)
        sys.modules["src.plugins.gokz.api.helper"] = types.SimpleNamespace(fetch_json=None)
        cls.cs2kz = load_module("src.plugins.gokz.api.cs2kz", ROOT / "src/plugins/gokz/api/cs2kz.py")

    def test_game_aliases(self):
        self.assertEqual(self.game.format_game("2"), "cs2kz")
        self.assertEqual(self.game.format_cs2kz_mode("vnl"), "vanilla")
        self.assertEqual(self.game.format_cs2kz_mode_label("classic"), "CKZ")

    def test_nub_and_pro_fields(self):
        record = {"teleports": 4, "nub_points": 12.5, "nub_rank": 3, "pro_points": 4.5, "pro_rank": 7}
        self.assertEqual(self.cs2kz.record_points(record), 12.5)
        self.assertEqual(self.cs2kz.record_rank(record), 3)
        self.assertEqual(self.cs2kz.record_points(record, True), 4.5)
        self.assertEqual(self.cs2kz.record_rank(record, True), 7)


if __name__ == "__main__":
    unittest.main()
