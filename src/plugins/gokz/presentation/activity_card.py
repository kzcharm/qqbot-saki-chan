"""Capture the website's shared profile activity calendar for QQ."""

import asyncio
import re
import secrets
from pathlib import Path
from urllib.parse import urlencode

import nonebot_plugin_localstore as store

from ..core.kz.player_card import _executor, capture_player_card, website_base_url


async def render_activity_card(data: dict) -> bytes:
    steamid, lang = str(data["steamid"]), data["lang"]
    if not re.fullmatch(r"\d{17}", steamid) or lang not in {"en", "zh-CN"}:
        raise ValueError("Invalid player or language")
    url = f"{website_base_url()}/cards/activity/{steamid}?{urlencode({'lang': lang})}"
    path = Path(store.get_cache_dir("activity_cards")) / f"{secrets.token_hex(16)}.png"

    def capture() -> bytes:
        try:
            capture_player_card(url, path, width=1200, test_id="activity-card", light_theme=True)
            return path.read_bytes()
        finally:
            path.unlink(missing_ok=True)

    return await asyncio.get_running_loop().run_in_executor(_executor, capture)
