"""Register the preserved QQ response handlers only for the QQ adapter."""

from typing import Any

from nonebot import on_command as register_command
from nonebot.adapters import Bot
from nonebot.adapters.qq import Bot as QQBot
from nonebot.rule import Rule


async def is_qq(bot: Bot) -> bool:
    return isinstance(bot, QQBot)


def on_command(command: str, *args: Any, **kwargs: Any) -> Any:
    original_rule = kwargs.pop("rule", None)
    kwargs["rule"] = Rule(is_qq) & original_rule
    # Preserve the original plugin/source location for command-panel discovery.
    kwargs["_depth"] = kwargs.get("_depth", 0) + 1
    return register_command(command, *args, **kwargs)
