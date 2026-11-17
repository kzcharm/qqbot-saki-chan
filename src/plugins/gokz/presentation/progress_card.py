"""Capture the existing website run-history charts for QQ."""

import asyncio
import re
import secrets
from pathlib import Path
from urllib.parse import urlencode

import nonebot_plugin_localstore as store

from ..core.kz.player_card import _executor, capture_player_card, website_base_url


async def render_progress_card(data: dict) -> bytes:
    steamid, map_id, scope = str(data["steamid"]), data["map_id"], data["scope"]
    if not re.fullmatch(r"\d{17}", steamid) or not isinstance(map_id, int) or map_id <= 0 or scope not in {"OVR", "KZT", "SKZ", "VNL"}:
        raise ValueError("Invalid player, map, or scope")
    url = f"{website_base_url()}/cards/run-history/{steamid}?{urlencode({'mapId': map_id, 'mapName': data['map_name'], 'scope': scope, 'lang': 'zh-CN'})}"
    path = Path(store.get_cache_dir("progress_cards")) / f"{secrets.token_hex(16)}.png"

    def capture() -> bytes:
        try:
            capture_player_card(url, path, width=1200, test_id="run-history-card", timezone_id="Asia/Shanghai")
            return path.read_bytes()
        finally:
            path.unlink(missing_ok=True)

    return await asyncio.get_running_loop().run_in_executor(_executor, capture)
