import importlib.util
import sys
import types
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class TestDailyMapMessage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for name in ("src", "src.plugins", "src.plugins.gokz", "src.plugins.gokz.core", "src.plugins.gokz.db"):
            sys.modules.setdefault(name, types.ModuleType(name))
        sys.modules["src.plugins.gokz.db.models"] = types.SimpleNamespace(DailyMapAssignment=object)
        load_module("src.plugins.gokz.core.keyboard", ROOT / "src/plugins/gokz/core/keyboard.py")
        cls.daily_message = load_module(
            "src.plugins.gokz.core.daily_map_message",
            ROOT / "src/plugins/gokz/core/daily_map_message.py",
        )

    def test_renders_independently_selected_copy_map_links_and_retrieve_button(self):
        assignments = {
            "improvement": types.SimpleNamespace(map_name="kz_old map", map_tier=3),
            "new": types.SimpleNamespace(map_name="kz_new", map_tier=5),
        }

        with patch.object(
            self.daily_message.random,
            "choice",
            side_effect=(
                self.daily_message.DAILY_INTROS[0],
                self.daily_message.NEW_MAP_INTROS[0],
                self.daily_message.IMPROVEMENT_MAP_INTROS[0],
                self.daily_message.DAILY_OUTROS[0],
            ),
        ):
            message = self.daily_message.daily_map_message(assignments, date(2026, 8, 26))

        self.assertEqual([segment.type for segment in message], ["markdown", "keyboard"])
        content = message[0].data["markdown"].content
        self.assertEqual(len(self.daily_message.DAILY_INTROS), 20)
        self.assertEqual(len(self.daily_message.NEW_MAP_INTROS), 20)
        self.assertEqual(len(self.daily_message.IMPROVEMENT_MAP_INTROS), 20)
        self.assertEqual(len(self.daily_message.DAILY_OUTROS), 20)
        self.assertIn("# 今日地图", content)
        self.assertNotIn("# 今日地图 ·", content)
        self.assertIn("📅 2026-08-26 · 今日地图来咯！", content)
        self.assertIn("🗺️ 开荒新图 kz_new T5！", content)
        self.assertIn("🔥 挑战旧图 kz_old map T3！", content)
        self.assertIn("🎯 今日份KZ安排完毕，开跳！", content)
        self.assertIn("## 挑战旧图", content)
        self.assertIn("## 开荒新图", content)
        self.assertLess(content.index("## 开荒新图"), content.index("## 挑战旧图"))
        self.assertIn("[kz_old map](https://gokz.top/maps/kz_old%20map/maptop) · T3", content)
        self.assertIn("[kz_new](https://gokz.top/maps/kz_new/maptop) · T5", content)
        self.assertNotIn("NUB 完成者", content)
        button = message[1].data["keyboard"].content.rows[0].buttons[0]
        self.assertEqual(button.render_data.label, "查看我的今日地图")
        self.assertEqual(button.action.data, "/daily")
        self.assertTrue(button.action.enter)


if __name__ == "__main__":
    unittest.main()
