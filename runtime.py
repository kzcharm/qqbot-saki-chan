"""Select independently configured NoneBot adapters."""

from typing import Any


def enabled_platforms(config: Any) -> tuple[str, ...]:
    configured = tuple(
        name
        for name, key in (("qq", "qq_bots"), ("discord", "discord_bots"))
        if getattr(config, key, None)
    )
    requested = getattr(config, "bot_platforms", None)
    if requested is None:
        return configured
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
