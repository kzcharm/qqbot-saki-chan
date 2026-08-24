import importlib.util
from pathlib import Path
import unittest

import nonebot

nonebot.init()

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("command_panel_under_test", ROOT / "src/plugins/gokz/core/command_panel.py")
assert SPEC and SPEC.loader
command_panel = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(command_panel)

COMMAND_DESCRIPTIONS = command_panel.COMMAND_DESCRIPTIONS
PANEL_ITEM_LIMIT = command_panel.PANEL_ITEM_LIMIT
_panel_payload = command_panel._panel_payload


class TestCommandPanel(unittest.TestCase):
    def test_help_image_descriptions_are_used(self):
        self.assertEqual(COMMAND_DESCRIPTIONS["pb"], "查询地图个人最佳")
        self.assertEqual(COMMAND_DESCRIPTIONS["wr"], "查询地图世界记录")
        self.assertEqual(COMMAND_DESCRIPTIONS["profile"], "查看玩家资料与链接")

    def test_panel_payload_contains_descriptions(self):
        panel = _panel_payload([("/help", "查看帮助", False)], 1)
        self.assertEqual(panel["remark"], "gokz-qqbot commands 1")
        self.assertEqual(panel["items"][0]["desc"], "查看帮助")
