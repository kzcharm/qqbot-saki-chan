"""Select independently configured NoneBot adapters from files or process env."""

import json
import os
from typing import Any


def enabled_platforms(config: Any) -> tuple[str, ...]:
    configured = []
    for name in ("qq", "discord"):
        value = getattr(config, name + "_bots", None)
        if value is None:
            value = os.getenv(name.upper() + "_BOTS", "[]")
        if isinstance(value, str):
            value = json.loads(value)
        if value:
            configured.append(name)
    requested = getattr(config, "bot_platforms", None)
    if requested is None:
        requested = os.getenv("BOT_PLATFORMS")
    if requested is None:
        if not configured:
            raise ValueError(
                "Configure QQ_BOTS and/or DISCORD_BOTS before starting the bot"
            )
        return tuple(configured)
    names = tuple(
        dict.fromkeys(
            name.strip().lower() for name in requested.split(",") if name.strip()
        )
    )
    if not names or set(names) - {"qq", "discord"}:
        raise ValueError("BOT_PLATFORMS must contain qq, discord, or qq,discord")
    for name in names:
        if name not in configured:
            raise ValueError(f"{name.upper()}_BOTS must be configured for {name}")
    return names
