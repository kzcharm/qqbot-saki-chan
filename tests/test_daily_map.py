import importlib.util
import sys
import types
import unittest
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def package(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules[name] = module


def load_daily_map_module():
    package("src", ROOT / "src")
    package("src.plugins", ROOT / "src/plugins")
    package("src.plugins.gokz", ROOT / "src/plugins/gokz")
    package("src.plugins.gokz.api", ROOT / "src/plugins/gokz/api")
    package("src.plugins.gokz.core", ROOT / "src/plugins/gokz/core")
    package("src.plugins.gokz.db", ROOT / "src/plugins/gokz/db")

    helper = types.ModuleType("src.plugins.gokz.api.helper")
    helper.fetch_json = None
    sys.modules[helper.__name__] = helper
    db = types.ModuleType("src.plugins.gokz.db.db")
    db.engine = object()
    sys.modules[db.__name__] = db
    models = types.ModuleType("src.plugins.gokz.db.models")
    models.DailyMapAssignment = object
    models.DailyMapCache = object
    sys.modules[models.__name__] = models

    spec = importlib.util.spec_from_file_location(
        "src.plugins.gokz.core.daily_map",
        ROOT / "src/plugins/gokz/core/daily_map.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


daily_map = load_daily_map_module()


class CapturingRandom:
    def __init__(self):
        self.calls = []

    def choices(self, population, weights, k):
        self.calls.append(list(weights))
        return [population[0]]


class DailyMapSelectionTest(unittest.TestCase):
    def test_new_map_excludes_completed_maps_and_uses_finisher_weights(self):
        maps = [
            {"id": 1, "name": "kz_one", "tier": 1},
            {"id": 2, "name": "kz_two", "tier": 1},
            {"id": 3, "name": "kz_done", "tier": 2},
        ]
        rng = CapturingRandom()

        selected = daily_map.choose_new_map(maps, {3}, {1: 1, 2: 10, 3: 100}, rng)

        self.assertEqual(selected["id"], 1)
        self.assertEqual(rng.calls[1], [2.0, 11.0])

    def test_improvement_excludes_recent_pbs_and_favors_low_points_old_popular_maps(self):
        now = datetime(2026, 8, 26)
        maps = [
            {"id": 1, "name": "kz_high_points", "tier": 1},
            {"id": 2, "name": "kz_low_points", "tier": 1},
            {"id": 3, "name": "kz_recent", "tier": 1},
        ]
        pbs = [
            {"map_id": 1, "points": 900, "updated_on": "2026-06-01T00:00:00Z"},
            {"map_id": 2, "points": 100, "updated_on": "2025-08-01T00:00:00Z"},
            {"map_id": 3, "points": 1, "updated_on": "2026-08-20T00:00:00Z"},
        ]
        rng = CapturingRandom()

        selected = daily_map.choose_improvement_map(maps, pbs, {1: 1, 2: 100, 3: 1}, now, rng)

        self.assertEqual(selected["id"], 1)
        self.assertEqual(len(rng.calls[1]), 2)
        self.assertLess(rng.calls[1][0], rng.calls[1][1])

    def test_tier_draw_uses_player_completion_percentages(self):
        maps = [
            {"id": 1, "name": "kz_tier_one_done", "tier": 1},
            {"id": 2, "name": "kz_tier_one_open", "tier": 1},
            {"id": 3, "name": "kz_tier_two_done", "tier": 2},
        ]
        pbs = [
            {"map_id": 1, "points": 100, "updated_on": "2025-01-01T00:00:00Z"},
            {"map_id": 3, "points": 100, "updated_on": "2025-01-01T00:00:00Z"},
        ]
        rng = CapturingRandom()

        daily_map.choose_improvement_map(maps, pbs, {1: 1, 3: 1}, datetime(2026, 8, 26), rng)

        self.assertEqual(rng.calls[0], [0.5, 1.0])


if __name__ == "__main__":
    unittest.main()
