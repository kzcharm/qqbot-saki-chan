import json
import subprocess
from datetime import datetime
from pathlib import Path

from src.plugins.gokz.core.kreedz import format_kzmode
from src.plugins.gokz.core.steam_user import convert_steamid
from ..api.helper import fetch_json

GLOBAL_API_URL = "https://kztimerglobal.com/api/v2.0/"


async def update_map_data():
    url = f"{GLOBAL_API_URL}maps?limit=2000"
    save_path = Path("data/gokz_maps_data.json")
    save_path.parent.mkdir(parents=True, exist_ok=True)

    # fetch and save json
    data = await fetch_json(url)
    with save_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # git pull the map-images repo
    repo_path = Path("data/map-images")
    if repo_path.exists():
        subprocess.run(["git", "pull"], cwd=repo_path, check=True)


async def fetch_global_stats(steamid64, mode_str, has_tp=True) -> list:
    steamid64 = convert_steamid(steamid64, 64)
    params = {
        'steamid64': steamid64,
        'tickrate': 128,
        'stage': 0,
        'modes_list_string': mode_str,
        'limit': 10000,
        'has_teleports': str(has_tp).lower(),
    }
    data = await fetch_json(f"{GLOBAL_API_URL}records/top", params=params)
    return data


async def fetch_personal_recent(steamid64, mode='kzt'):
    steamid64 = convert_steamid(steamid64, 64)
    mode = format_kzmode(mode)

    data_with_tp = await fetch_global_stats(steamid64, mode, True)
    data_without_tp = await fetch_global_stats(steamid64, mode, False)
    data = data_with_tp + data_without_tp

    for item in data:
        item["created_on_datetime"] = datetime.fromisoformat(item["updated_on"])
    sorted_data = sorted(data, key=lambda x: x["created_on_datetime"], reverse=True)

    return sorted_data[0]


async def fetch_personal_best(steamid64, map_name, mode='kzt', has_tp=True):
    steamid64 = convert_steamid(steamid64, 64)
    mode = format_kzmode(mode)

    params = {
        'steamid64': str(steamid64),
        'map_name': map_name,
        'stage': 0,
        'modes_list_string': mode,
        'has_teleports': str(has_tp).lower()
    }

    url = "https://kztimerglobal.com/api/v2.0/records/top"
    data = await fetch_json(url, params=params)
    if data:
        return data[0]
    else:
        return None


async def fetch_personal_bans(steamid64):
    steamid64 = convert_steamid(steamid64, 64)

    params = {
        'steamid64': str(steamid64),
    }

    url = "https://kztimerglobal.com/api/v2.0/bans"
    data = await fetch_json(url, params=params)
    if data:
        return data
    else:
        return None


async def fetch_world_record(map_name, mode='kzt', has_tp=True):
    mode = format_kzmode(mode)
    params = {
        'map_name': map_name,
        'has_teleports': str(has_tp).lower(),
        'stage': 0,
        'modes_list_string': mode,
        'place_top_at_least': 1
    }

    data = await fetch_json(f"{GLOBAL_API_URL}records/top/recent", params=params)
    return data[0]


async def fetch_overall_world_record(map_name, mode='kzt'):
    """Fetch Overall WR (not TP-specific) for a map"""
    mode = format_kzmode(mode)
    params = {
        'map_name': map_name,
        'tickrate': 128,
        'overall': 'true',
        'stage': 0,
        'modes_list_string': mode,
        'limit': 1
    }

    data = await fetch_json(f"{GLOBAL_API_URL}records/top", params=params)
    if not data or len(data) == 0:
        raise IndexError("No overall WR found")
    return data[0]


async def fetch_personal_purity(steamid64, mode='kzt', exclusive=False) -> dict:
    server_id = [1683, 1633, 1393]

    steamid64 = convert_steamid(steamid64, 64)
    mode = format_kzmode(mode)

    data_with_tp = await fetch_global_stats(steamid64, mode, True)
    data_without_tp = await fetch_global_stats(steamid64, mode, False)
    data = data_with_tp + data_without_tp

    maps = [f"{record['map_name']} {'TP' if record['teleports'] else 'PRO'}" for record in data if record['server_id'] != 1683]

    if exclusive:
        count = sum(1 for item in data if item.get('server_id') in server_id)
    else:
        count = sum(1 for item in data if item.get('server_id') == server_id[0])

    return {
        'name': data[0]['player_name'],
        'steamid64': steamid64,
        'count': count,
        'total': len(data),
        'percentage': count / len(data),
        'maps': maps,
    }
