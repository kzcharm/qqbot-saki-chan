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
        with patch.object(self.gokz_top, "fetch_json", AsyncMock(return_value=[RECORD])) as fetch:
            record = await self.gokz_top.fetch_personal_best(
                "76561198000000000", "kz_test", "ovr", "NUB"
            )

        self.assertEqual(record["player_name"], "Runner")
        self.assertEqual(record["steam_id"], "76561198000000000")
        self.assertEqual(
            fetch.await_args.kwargs["params"],
            {
                "identifier": "76561198000000000",
                "map_name": "kz_test",
                "scope": "OVR",
                "type": "NUB",
                "stage": 0,
                "limit": 1,
            },
        )

    async def test_recent_personal_best_prefers_newest_created_time(self):
        pro_record = {**RECORD, "created_on": "2026-08-26T13:00:00+00:00"}
        with patch.object(
            self.gokz_top, "fetch_json", AsyncMock(side_effect=[[RECORD], [pro_record]])
        ):
            record = await self.gokz_top.fetch_personal_recent("76561198000000000", "KZT")

        self.assertEqual(record["created_on"], pro_record["created_on"])

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
