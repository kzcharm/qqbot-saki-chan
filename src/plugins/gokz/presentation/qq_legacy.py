"""Register the preserved QQ response handlers only for the QQ adapter."""

from typing import Any

from nonebot import get_driver
from nonebot import on_command as register_command
from nonebot.adapters import Bot, Event
from nonebot.adapters.qq import Bot as QQBot
from nonebot.permission import SUPERUSER, Permission
from nonebot.rule import Rule


async def is_qq(bot: Bot) -> bool:
    return isinstance(bot, QQBot)


async def is_qq_root(bot: Bot, event: Event) -> bool:
    if not isinstance(bot, QQBot):
        return False
    account = event.get_user_id()
    roots = get_driver().config.superusers
    return account in roots or f"qq:{account}" in roots


def on_command(command: str, *args: Any, **kwargs: Any) -> Any:
    if kwargs.get("permission") is SUPERUSER:
        kwargs["permission"] = Permission(is_qq_root)
    original_rule = kwargs.pop("rule", None)
    kwargs["rule"] = Rule(is_qq) & original_rule
    # Preserve the original plugin/source location for command-panel discovery.
    kwargs["_depth"] = kwargs.get("_depth", 0) + 1
    return register_command(command, *args, **kwargs)
