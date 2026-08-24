import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "profile_under_test", ROOT / "src/plugins/gokz/core/profile.py"
)
assert SPEC and SPEC.loader
profile = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(profile)


class TestProfileMarkdown(unittest.TestCase):
    player = {
        "name": "Steam Name",
        "alias": "Player Alias",
        "steamid64": "76561198000000000",
        "custom_id": "player_alias",
        "country": "cn",
        "primary_mode": "KZT",
        "rank": 42,
        "rating": 7.5,
        "points": 12345,
    }

    def test_complete_profile_includes_core_details_and_links(self):
        content = profile.profile_markdown(
            self.player, [{"platform": "Bilibili", "url": "https://space.bilibili.com/42"}]
        )

        self.assertIn("## Player Alias", content)
        self.assertIn("国家/地区: 中国", content)
        self.assertIn("全球排名: `#42`", content)
        self.assertIn("[GOKZ.TOP](https://gokz.top/profile/player_alias/records)", content)
        self.assertIn("[Steam](https://steamcommunity.com/profiles/76561198000000000)", content)
        self.assertIn("[Bilibili](https://space.bilibili.com/42)", content)

    def test_missing_optional_stats_and_social_links_are_omitted(self):
        player = {"name": "No Stats", "steamid64": "76561198000000001"}
        content = profile.profile_markdown(player, [])

        self.assertNotIn("国家/地区", content)
        self.assertNotIn("全球排名", content)
        self.assertNotIn("Rating", content)
        self.assertNotIn("积分", content)
        self.assertNotIn("Bilibili", content)
        self.assertIn("https://gokz.top/profile/76561198000000001/records", content)

    def test_only_bilibili_platform_creates_bilibili_link(self):
        content = profile.profile_markdown(
            self.player,
            [
                {"platform": "YouTube", "url": "https://youtube.com/example"},
                {"platform": "BILIBILI", "url": "https://space.bilibili.com/84"},
            ],
        )

        self.assertIn("[Bilibili](https://space.bilibili.com/84)", content)
        self.assertNotIn("youtube.com", content)

    def test_extended_profile_information_and_achievements_are_rendered(self):
        player = self.player | {
            "created_at": "2022-08-24T12:00:00Z",
            "last_played_at": "2026-08-23T18:00:00Z",
            "rating": None,
            "favorite_server": {
                "label": "AXE GOKZ",
                "server_group": {"custom_id": "axekz"},
            },
        }
        content = profile.profile_markdown(
            player,
            stats={"playtime": {"total_seconds": 2649600}},
            jumpstats={"data": [{"distance": 281.8}]},
            achievements={
                "data": [
                    {"tournament": {"name": "AXE Major"}, "placement": 1},
                    {"tournament": {"name": "Green Cup"}, "placement": 4},
                ]
            },
            leaderboard={"rank": 902, "rank_regional": 176, "region": "EU", "rating": 7.675, "points": 80440},
        )

        self.assertIn("加入时间: `2022-08-24`", content)
        self.assertIn("最近游玩: `2026-08-23`", content)
        self.assertIn("游玩时长: `736.0 小时`", content)
        self.assertIn("地区排名: `EU #176`", content)
        self.assertIn("Rating: `7.67`", content)
        self.assertIn("Long Jump: `281.80 units`", content)
        self.assertIn("[AXE GOKZ](https://gokz.top/servers/group/axekz)", content)
        self.assertIn("勋章: AXE Major 冠军 · Green Cup 四强", content)

    def test_country_code_uses_chinese_name_and_unknown_code_falls_back(self):
        self.assertEqual(profile.country_name_zh("DE"), "德国")
        self.assertEqual(profile.country_name_zh("XX"), "XX")
