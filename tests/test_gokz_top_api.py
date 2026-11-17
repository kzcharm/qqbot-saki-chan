import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


RECORD = {
    "uuid": "record-uuid",
    "player": {"steamid64": "76561198000000000", "display_name": "Runner"},
    "server_name": "AXE GOKZ",
    "map_name": "kz_test",
    "created_on": "2026-08-26T12:00:00+00:00",
    "time": 12.5,
    "teleports": 3,
    "points": 100,
}
RANKS = {"data": [{"record_uuid": RECORD["uuid"], "rank": 42, "total_count": 1280}]}


class TestGOKZTopAPI(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        for name in ("src", "src.plugins", "src.plugins.gokz", "src.plugins.gokz.api"):
            sys.modules.setdefault(name, types.ModuleType(name))
        sys.modules["src.plugins.gokz.api.helper"] = types.SimpleNamespace(fetch_json=None)
        cls.gokz_top = load_module(
            "src.plugins.gokz.api.gokz_top", ROOT / "src/plugins/gokz/api/gokz_top.py"
        )

    async def test_personal_best_uses_documented_v1_parameters(self):
        with patch.object(self.gokz_top, "fetch_json", AsyncMock(side_effect=[[RECORD], RANKS])) as fetch:
            record = await self.gokz_top.fetch_personal_best(
                "76561198000000000", "kz_test", "ovr", "NUB"
            )

        self.assertEqual(record["player_name"], "Runner")
        self.assertEqual(record["steam_id"], "76561198000000000")
        self.assertEqual((record["rank"], record["total_count"]), (42, 1280))
        self.assertEqual(
            fetch.await_args_list[0].kwargs["params"],
            {
                "identifier": "76561198000000000",
                "map_name": "kz_test",
                "scope": "OVR",
                "type": "NUB",
                "stage": 0,
                "limit": 1,
            },
        )
        self.assertEqual(fetch.await_args.args, (f"{self.gokz_top.BASE_URL}/records/rank",))
        self.assertEqual(fetch.await_args.kwargs["params"], {
            "uuid_list": [RECORD["uuid"]], "scope": "OVR", "type": "NUB",
        })

    async def test_pro_best_uses_pro_rank_bucket(self):
        with patch.object(self.gokz_top, "fetch_json", AsyncMock(side_effect=[[RECORD], RANKS])) as fetch:
            record = await self.gokz_top.fetch_personal_best(
                "76561198000000000", "kz_test", "kz_timer", "PRO"
            )
        self.assertEqual(record["rank"], 42)
        self.assertEqual(fetch.await_args.kwargs["params"]["scope"], "KZT")
        self.assertEqual(fetch.await_args.kwargs["params"]["type"], "PRO")

    async def test_recent_personal_best_prefers_newest_created_time(self):
        pro_record = {**RECORD, "teleports": 0, "created_on": "2026-08-26T13:00:00+00:00"}
        with patch.object(
            self.gokz_top, "fetch_json", AsyncMock(side_effect=[[RECORD], [pro_record], RANKS])
        ) as fetch:
            record = await self.gokz_top.fetch_personal_recent("76561198000000000", "KZT")

        self.assertEqual(record["created_on"], pro_record["created_on"])
        self.assertEqual(record["rank"], 42)
        self.assertEqual(fetch.await_args.kwargs["params"]["type"], "NUB")

    async def test_empty_records_skip_rank_lookup(self):
        with patch.object(self.gokz_top, "fetch_json", AsyncMock(return_value=[])) as fetch:
            self.assertIsNone(await self.gokz_top.fetch_personal_best("76561198000000000", "kz_test", "OVR", "NUB"))
            self.assertIsNone(await self.gokz_top.fetch_personal_recent("76561198000000000", "OVR"))
        self.assertEqual(fetch.await_count, 3)

    async def test_rank_unavailable_keeps_record(self):
        for response in (None, {"detail": "Unavailable"}, {"data": []}, {"data": [None]},
                         {"data": [{"record_uuid": "other", "rank": 1, "total_count": 1}]},
                         {"data": [{"record_uuid": RECORD["uuid"], "rank": None, "total_count": None}]}):
            with self.subTest(response=response), patch.object(
                self.gokz_top, "fetch_json", AsyncMock(side_effect=[[RECORD], response])
            ):
                record = await self.gokz_top.fetch_personal_best("76561198000000000", "kz_test", "OVR", "NUB")
                self.assertEqual(record["time"], RECORD["time"])
                self.assertIsNone(record.get("rank"))

    async def test_world_record_uses_time_sorting(self):
        with patch.object(self.gokz_top, "fetch_json", AsyncMock(return_value=[RECORD])) as fetch:
            await self.gokz_top.fetch_world_record("kz_test", "kz_timer", "PRO")

        self.assertEqual(fetch.await_args.kwargs["params"]["scope"], "KZT")
        self.assertEqual(fetch.await_args.kwargs["params"]["sort_by"], "time")
        self.assertEqual(fetch.await_args.kwargs["params"]["sort_order"], "asc")

    async def test_bans_use_public_v1_endpoint_and_unwrap_data(self):
        response = {"data": [{"uuid": "ban-uuid", "ban_type": "Cheating"}], "count": 1}
        with patch.object(self.gokz_top, "fetch_json", AsyncMock(return_value=response)) as fetch:
            bans = await self.gokz_top.fetch_personal_bans("76561198000000000")

        self.assertEqual(bans, response["data"])
        self.assertEqual(fetch.await_args.kwargs["params"], {"steamid64": "76561198000000000"})
        self.assertNotIn("headers", fetch.await_args.kwargs)

    async def test_invalid_history_response_raises_api_error(self):
        with patch.object(self.gokz_top, "fetch_json", AsyncMock(return_value=None)):
            with self.assertRaises(self.gokz_top.GOKZTopAPIError):
                await self.gokz_top.fetch_run_history("76561198000000000", 1, "OVR", "NUB")


if __name__ == "__main__":
    unittest.main()
