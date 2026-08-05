from datetime import datetime
from typing import Any
from urllib.parse import quote

from src.plugins.gokz.core.game import format_cs2kz_mode
from src.plugins.gokz.core.steam_user import convert_steamid
from .helper import fetch_json

CS2KZ_API_URL = "https://api.cs2kz.org"


def cs2kz_player_id(steamid: str) -> str:
    return str(convert_steamid(steamid, 2))


def record_created_on(record: dict[str, Any]) -> str:
    try:
        timestamp_ms = int(record["id"].replace("-", "")[:12], 16)
        return datetime.fromtimestamp(timestamp_ms / 1000).strftime("%Y-%m-%dT%H:%M:%S")
    except (KeyError, TypeError, ValueError, OSError):
        return ""


def record_points(record: dict[str, Any], pro: bool | None = None) -> float | None:
    if pro is None:
        pro = record.get("teleports", 0) == 0
    return record.get("pro_points") if pro else record.get("nub_points")


def record_rank(record: dict[str, Any], pro: bool | None = None) -> int | None:
    if pro is None:
        pro = record.get("teleports", 0) == 0
    return record.get("pro_rank") if pro else record.get("nub_rank")


async def fetch_player(player: str) -> dict[str, Any] | None:
    data = await fetch_json(f"{CS2KZ_API_URL}/players/{quote(player, safe='')}")
    return data if isinstance(data, dict) and data.get("id") else None


async def search_players(name: str, limit: int = 10) -> list[dict[str, Any]]:
    data = await fetch_json(f"{CS2KZ_API_URL}/players", params={"name": name, "limit": limit})
    return data.get("values", []) if isinstance(data, dict) else []


async def fetch_map(map_name: str) -> dict[str, Any] | None:
    data = await fetch_json(f"{CS2KZ_API_URL}/maps", params={"name": map_name, "state": "approved", "limit": 10})
    maps = data.get("values", []) if isinstance(data, dict) else []
    if not maps:
        return None
    return next((item for item in maps if item.get("name", "").lower() == map_name.lower()), maps[0])


def find_course(map_data: dict[str, Any] | None, course_name: str) -> str:
    courses = map_data.get("courses", []) if map_data else []
    course_name = course_name or "Main"
    lowered = course_name.lower()
    return next((course["name"] for course in courses if course.get("name", "").lower() == lowered), next((course["name"] for course in courses if lowered in course.get("name", "").lower()), course_name))


async def fetch_records(*, player: str | None = None, map_name: str | None = None, course: str | None = None, mode: str = "classic", top: bool | None = None, has_teleports: bool | None = None, max_rank: int | None = None, sort_by: str = "submission-date", sort_order: str = "descending", limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"mode": format_cs2kz_mode(mode), "sort_by": sort_by, "sort_order": sort_order, "limit": limit, "offset": offset}
    for key, value in {"player": player, "map": map_name, "course": course, "top": top, "has_teleports": has_teleports, "max_rank": max_rank}.items():
        if value is not None:
            params[key] = str(value).lower() if isinstance(value, bool) else value
    data = await fetch_json(f"{CS2KZ_API_URL}/records", params=params)
    return data.get("values", []) if isinstance(data, dict) else []


async def fetch_profile_records(player: str, mode: str, limit: int = 10000) -> list[dict[str, Any]]:
    return await fetch_records(player=player, mode=mode, top=True, limit=limit)
