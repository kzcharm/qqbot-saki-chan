"""Capture the public website server-playtime card for QQ."""

import asyncio
import re
import secrets
from pathlib import Path
from urllib.parse import urlencode

import nonebot_plugin_localstore as store

from ..core.kz.player_card import _executor, capture_player_card, website_base_url


async def render_server_playtime_card(data: dict) -> bytes:
    steamid, period = str(data["steamid"]), data["preset"]
    if not re.fullmatch(r"\d{17}", steamid) or period not in {"all", "recent"}:
        raise ValueError("Invalid player or period")
    url = f"{website_base_url()}/cards/server-playtime/{steamid}?{urlencode({'period': period, 'lang': 'zh-CN'})}"
    path = Path(store.get_cache_dir("server_playtime_cards")) / f"{secrets.token_hex(16)}.png"

    def capture() -> bytes:
        try:
            capture_player_card(url, path, width=1200, test_id="server-playtime-card", light_theme=True)
            return path.read_bytes()
        finally:
            path.unlink(missing_ok=True)

    return await asyncio.get_running_loop().run_in_executor(_executor, capture)
