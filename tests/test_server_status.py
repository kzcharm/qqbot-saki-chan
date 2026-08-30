import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "server_status_under_test", ROOT / "src/plugins/gokz/core/server_status.py"
)
assert SPEC and SPEC.loader
server_status = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = server_status
SPEC.loader.exec_module(server_status)


SERVERS = [
    {
        "ip": "127.0.0.1",
        "port": 27015,
        "id": "online-server",
        "region": "EU",
        "map_tier": 7,
        "group": {"name": "AXE GOKZ", "custom_id": "axekz"},
        "live_status": {
            "hostname": "AXE GOKZ #B01",
            "map": "kz_test",
            "player_count": 1,
            "max_players": 16,
            "is_online": True,
            "players": [{
                "tag": "[KZT]",
                "name": "Runner",
                "timer_time": 125.9,
                "score": 550,
                "status": "in_progress",
                "teleports": 1,
                "is_paused": True,
            }],
        },
    },
    {
        "ip": "127.0.0.2",
        "port": 27016,
        "id": "offline-server",
        "region": "EU",
        "group": {"name": "AXE GOKZ", "custom_id": "axekz"},
        "live_status": {"is_online": False},
    },
    {
        "ip": "127.0.0.3",
        "port": 27017,
        "id": "other-server",
        "region": "CN",
        "group": {"name": "Other KZ", "custom_id": "other"},
        "live_status": {"player_count": 0, "is_online": True},
    },
    {
        "ip": "127.0.0.4",
        "port": 27018,
        "id": "axe-cn-server",
        "region": "CN",
        "group": {"name": "AXE GOKZ", "custom_id": "axekz"},
        "live_status": {"player_count": 0, "is_online": True},
    },
]


class TestServerStatusMarkdown(unittest.TestCase):
    def test_group_list_includes_slugs_server_counts_and_players(self):
        content = server_status.server_groups_markdown(SERVERS)

        self.assertIn("## CN", content)
        self.assertIn("**Other KZ** (`other`) · 1 服务器 · 0 玩家", content)
        self.assertIn("## EU", content)
        self.assertLess(content.index("## CN"), content.index("## EU"))
        self.assertIn("**AXE GOKZ** (`axekz`) · 1 服务器 · 1 玩家", content)
        cn_section = content[content.index("## CN"):content.index("## EU")]
        self.assertLess(cn_section.index("AXE GOKZ"), cn_section.index("Other KZ"))

    def test_group_status_includes_clan_tags_without_timer_status(self):
        content = server_status.server_group_status_markdown(SERVERS, "AXEKZ")

        self.assertIn("# AXE GOKZ 服务器状态", content)
        self.assertIn("## EU", content)
        self.assertIn(
            "[**AXE GOKZ #B01**](https://gokz.top/servers/group/axekz) · *kz_test* · T7",
            content,
        )
        self.assertIn("`[KZT] Runner`", content)
        self.assertNotIn("02:05", content)
        self.assertNotIn("55.0%", content)
        self.assertNotIn("127.0.0.2", content)

    def test_player_label_only_includes_the_clan_tag_and_name(self):
        self.assertEqual(
            server_status.player_label({
                "tag": "[SKZ]", "name": "Runner", "timer_time": 61,
                "score": 1000, "status": "in_progress", "teleports": 0,
            }),
            "`[SKZ] Runner`",
        )
        self.assertEqual(
            server_status.player_label({"name": "Idle", "status": "not_started"}),
            "`Idle`",
        )

    def test_servers_with_more_than_five_players_show_names_without_tags(self):
        crowded = [dict(server) for server in SERVERS]
        crowded[0]["live_status"] = dict(crowded[0]["live_status"])
        crowded[0]["live_status"]["players"] = [
            {"tag": "[KZT]", "name": f"Runner {index}"}
            for index in range(1, 7)
        ]

        content = server_status.server_group_status_markdown(crowded, "axekz")

        self.assertIn("`Runner 1`", content)
        self.assertIn("`Runner 6`", content)
        self.assertNotIn("[KZT] Runner 1", content)

    def test_unknown_group_returns_none(self):
        self.assertIsNone(server_status.server_group_status_markdown(SERVERS, "missing"))

    def test_group_name_resolves_only_when_unambiguous(self):
        self.assertEqual(server_status.resolve_server_group_slug(SERVERS, "axe gokz"), "axekz")
        ambiguous = [
            {"group": {"name": "Shared", "custom_id": "first"}},
            {"group": {"name": "Shared", "custom_id": "second"}},
        ]
        self.assertIsNone(server_status.resolve_server_group_slug(ambiguous, "shared"))
        self.assertEqual(server_status.resolve_server_group_slug(ambiguous, "first"), "first")

    def test_cn_choices_include_each_online_group_once(self):
        choices = server_status.cn_server_group_choices(SERVERS)

        self.assertEqual(choices, [("axekz", "AXE GOKZ"), ("other", "Other KZ")])


if __name__ == "__main__":
    unittest.main()
