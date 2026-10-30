"""Compare complete QQ payloads with captured pre-refactor responses.

The adapters execute the real shared service; only external API calls, identity,
clock and random greeting choices are fixed. Golden files were captured before
extracting the QQ handlers' feature logic.
"""

import asyncio
import importlib
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
TEMP = tempfile.TemporaryDirectory()
os.environ["BOT_DATABASE_PATH"] = str(Path(TEMP.name) / "bot.sqlite3")
import nonebot

nonebot.init(_env_file=None, driver="~httpx+~websockets", log_level="ERROR")
assert nonebot.load_plugin("src.plugins.gokz")
from nonebot.adapters.qq import Message
from src.plugins.gokz.application import service

STEAM = "76561197960278073"
MAP = {"id": "map-1", "name": "bkz_cakewalk", "authors": ["Author"]}
PLAYER = {
    "name": "Steam Name",
    "alias": "Player Name",
    "steamid64": STEAM,
    "primary_scope": "KZT",
}
RECORD = {
    "id": "run-1",
    "time": 61.25,
    "teleports": 2,
    "points": 123,
    "rating": 9.5,
    "map_tier": 1,
    "map_name": MAP["name"],
    "player_name": "Player Name",
    "server_name": "Test Server",
    "created_on": "2026-10-01T10:00:00Z",
    "mode": "KZT",
}
RANK = {
    "player": PLAYER,
    "scope": "KZT",
    "rank": 20,
    "rank_regional": 2,
    "region": "cn",
    "rating": 9.5,
    "points": 12345,
    "unique_map_finishes": 10,
    "wrs_nub": 1,
}
BANS = [
    {
        "ban_type": "bhop_hack",
        "player": {"display_name": "Player Name"},
        "notes": "Notes",
        "server": {"id": "server-1"},
        "created_at": "2026-10-01T10:00:00Z",
        "expires_at": None,
    }
]
STATS = {
    "steamid64": STEAM,
    "most_played_server": {
        "all_time": {
            "total_seconds": 7200,
            "entries": [{"label": "Test Server", "total_seconds": 7200}],
        }
    },
}
REVIEWS = {
    "count": 1,
    "data": [
        {
            "player": {"display_name": "Player Name"},
            "content": {
                "overall": 4,
                "visuals": 3,
                "gameplay": 5,
                "comment": {"text": "A good map"},
            },
        }
    ],
}
SERVER = {
    "ip": "127.0.0.1",
    "port": 27015,
    "group": {"custom_id": "axekz", "name": "AXE", "country": "CN"},
    "live_status": {
        "is_online": True,
        "hostname": "AXE Test",
        "map": MAP["name"],
        "player_count": 1,
        "max_players": 20,
        "players": [{"name": "Player Name"}],
    },
}


async def api(path, params=None, **kwargs):
    path = path.removeprefix("https://api.gokz.top/v1")
    params = params or kwargs
    if path == f"/players/{STEAM}":
        return dict(PLAYER)
    if "social-links" in path:
        return {"data": []} if path.startswith("/player-social") else []
    if path.endswith("/stats"):
        return STATS
    if path.endswith("/jumpstats") or path.endswith("/tournament-achievements"):
        return {"data": []}
    if path.startswith("/leaderboards/players"):
        return dict(RANK)
    if path == "/maps":
        return [MAP]
    if path == "/maps/reviews":
        return REVIEWS
    if path == "/players/search":
        return {"data": [PLAYER]}
    if path == "/servers":
        return {"data": [SERVER]}
    raise AssertionError(path)


class Finished(BaseException):
    pass


def normalize(outputs):
    messages = []
    for output in outputs:
        msg = Message(output)
        messages.append(
            [
                {
                    "type": seg.type,
                    "data": json.loads(
                        json.dumps(
                            seg.data,
                            default=lambda x: x.model_dump(exclude_none=True)
                            if hasattr(x, "model_dump")
                            else str(x),
                            ensure_ascii=False,
                        )
                    ),
                }
                for seg in msg
            ]
        )
    return messages


async def capture(module_name, command, text):
    module = importlib.import_module(f"src.plugins.gokz.plugins.{module_name}")
    matcher_name = {"ban": "ban_", "mp": "progress", "rank_update": "rank"}.get(
        command, command
    )
    matcher = getattr(module, matcher_name)
    fn = matcher.handlers[0].call
    outputs = []

    async def finish(message, **kwargs):
        outputs.append(message)
        raise Finished()

    cd = SimpleNamespace(
        error=None,
        steamid=STEAM,
        steamid2=None,
        qid="qq-user",
        mode="kzt",
        args=tuple(text.split()),
        update=command == "rank_update",
    )
    event = SimpleNamespace(
        get_user_id=lambda: "qq-user", group_id=None, group_openid=None
    )
    bot = SimpleNamespace(
        send=AsyncMock(side_effect=lambda ev, message: outputs.append(message))
    )
    arguments = {"event": event, "bot": bot, "args": Message(text)}
    import inspect

    arguments = {
        k: v for k, v in arguments.items() if k in inspect.signature(fn).parameters
    }
    with (
        patch.object(module, "CommandData", return_value=cd, create=True),
        patch.object(
            matcher,
            "send",
            AsyncMock(side_effect=lambda message, **kwargs: outputs.append(message)),
        ),
        patch.object(matcher, "finish", AsyncMock(side_effect=finish)),
        patch.object(service, "read", side_effect=api),
        patch.object(service, "binding", AsyncMock(return_value=STEAM)),
        patch.object(service, "preference", return_value="KZT"),
        patch.object(service, "get_maps", AsyncMock()),
        patch.object(service, "resolve_map_name", return_value=(MAP["name"], [])),
        patch.object(service, "fetch_personal_best", AsyncMock(return_value=RECORD)),
        patch.object(service, "fetch_world_record", AsyncMock(return_value=RECORD)),
        patch.object(service, "fetch_personal_recent", AsyncMock(return_value=RECORD)),
        patch.object(service, "fetch_personal_bans", AsyncMock(return_value=BANS)),
        patch.object(
            service, "fetch_run_history", AsyncMock(return_value={"data": [RECORD]})
        ),
        patch.object(service, "put_json", AsyncMock(return_value={})),
        patch.object(
            asyncio, "create_task", side_effect=lambda coroutine: coroutine.close()
        ),
    ):
        try:
            await fn(**arguments)
        except Finished:
            pass
    return normalize(outputs)


CASES = [
    ("general", "profile", ""),
    ("kzglobal", "pb", "cakewalk"),
    ("kzglobal", "wr", "cakewalk"),
    ("kzglobal", "pr", ""),
    ("kzglobal", "ban", ""),
    ("kzglobal", "rank", ""),
    ("kzglobal", "rank_update", ""),
    ("kzglobal", "review", "cakewalk"),
    ("kzglobal", "rate", "cakewalk"),
    ("gokz_top", "find", "Player"),
    ("gokz_top", "ccf", ""),
    ("gokz_top", "mp", "cakewalk"),
    ("gokz_top", "server", "axekz"),
]


async def main():
    values = {
        f"{module}/{command}": await capture(module, command, text)
        for module, command, text in CASES
    }
    expected = json.loads((ROOT / "tests/fixtures/qq_payloads.json").read_text())
    for name in values:
        assert values[name] == expected[name], (
            f"{name}: QQ payload differs from the original\n{values[name]}\n{expected[name]}"
        )
    print(f"{len(values)} original QQ payloads preserved through shared features")


if __name__ == "__main__":
    asyncio.run(main())
