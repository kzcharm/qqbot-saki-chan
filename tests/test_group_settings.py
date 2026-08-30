import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "group_settings_under_test", ROOT / "src/plugins/gokz/core/group_settings.py"
)
assert SPEC and SPEC.loader
group_settings = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(group_settings)


class Event:
    def __init__(self, group_openid=None, group_id=None):
        self.group_openid = group_openid
        self.group_id = group_id


class TestGroupSettings(unittest.TestCase):
    def test_group_openid_is_preferred_over_legacy_group_id(self):
        self.assertEqual(group_settings.group_chat_id(Event("openid", "legacy")), "openid")
        self.assertEqual(group_settings.group_chat_id(Event(group_id="legacy")), "legacy")
        self.assertIsNone(group_settings.group_chat_id(Event()))

    def test_group_info_includes_the_group_id_and_default_server(self):
        content = group_settings.group_info_markdown("openid", "axekz")

        self.assertIn("群组 ID: `openid`", content)
        self.assertIn("默认服务器组: `axekz`", content)

    def test_set_server_uses_the_current_group_for_one_argument(self):
        self.assertEqual(
            group_settings.set_server_target(("House of Climb",), "current-group"),
            ("current-group", "House of Climb"),
        )

    def test_set_server_accepts_an_explicit_group_id_without_a_group_event(self):
        self.assertEqual(
            group_settings.set_server_target(("target-group", "House", "of", "Climb"), None),
            ("target-group", "House of Climb"),
        )
        self.assertIsNone(group_settings.set_server_target(("axekz",), None))


if __name__ == "__main__":
    unittest.main()
