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
PANEL_EXCLUDED_COMMANDS = command_panel.PANEL_EXCLUDED_COMMANDS
_panel_payload = command_panel._panel_payload
_prioritize_commands = command_panel._prioritize_commands


class TestCommandPanel(unittest.TestCase):
    def test_help_image_descriptions_are_used(self):
        self.assertEqual(COMMAND_DESCRIPTIONS["pb"], "查询地图个人最佳")
        self.assertEqual(COMMAND_DESCRIPTIONS["wr"], "查询地图世界记录")
        self.assertEqual(COMMAND_DESCRIPTIONS["profile"], "查看玩家资料与链接")
        self.assertEqual(COMMAND_DESCRIPTIONS["daily"], "获取今日开荒与挑战地图")

    def test_panel_payload_contains_descriptions(self):
        panel = _panel_payload([("/help", "查看帮助", False)], 1)
        self.assertEqual(panel["remark"], "gokz-qqbot commands 1")
        self.assertEqual(panel["items"][0]["desc"], "查看帮助")

    def test_daily_command_is_prioritized_before_panel_limit_is_applied(self):
        commands = [(f"/command{i}", "测试", False) for i in range(PANEL_ITEM_LIMIT)]
        commands.append(("/daily", "获取今日开荒与挑战地图", False))

        self.assertEqual(_prioritize_commands(commands)[0][0], "/daily")

    def test_group_info_is_not_registered_in_the_command_panel(self):
        self.assertIn("group_info", PANEL_EXCLUDED_COMMANDS)
