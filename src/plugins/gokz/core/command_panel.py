"""Synchronise the QQ command panel with this plugin's NoneBot commands."""

from __future__ import annotations

import json
from typing import Any

from nonebot import get_driver, logger
from nonebot.adapters.qq import Bot
from nonebot.drivers import Request


PANEL_REMARK_PREFIX = "gokz-qqbot commands"
PANEL_ITEM_LIMIT = 20
PANEL_SCOPES = ("c2c", "group")
PANEL_EXCLUDED_COMMANDS = {"test", "markdown_test", "group_info"}
PANEL_HIDDEN_ALIASES = {"server"}
PANEL_FEATURED_COMMANDS = ("daily",)

# Derived from data/gokz/help.png. Keep descriptions short: QQ limits them to
# 30 characters and command names to 14 characters.
COMMAND_DESCRIPTIONS = {
    "help": "查看帮助",
    "bind": "绑定 SteamID",
    "mode": "切换默认 KZ 模式",
    "game": "切换默认游戏",
    "info": "查看已绑定账号信息",
    "profile": "查看玩家资料与链接",
    "kz": "生成玩家卡片",
    "pb": "查询地图个人最佳",
    "pr": "查询最近跳图记录",
    "wr": "查询地图世界记录",
    "rank": "查询 gokz.top 排名",
    "pk": "与他人进行 Rank PK",
    "server": "查看服务器组与实时状态",
    "mp": "查询地图进步情况",
    "daily": "获取今日开荒与挑战地图",
    "ccf": "查询常玩服务器",
    "find": "通过昵称查找玩家",
    "pw": "查询完美平台数据",
    "ban": "查询玩家封禁记录",
    "review": "查询地图评价",
    "rate": "为地图评分",
    "api": "查询 GlobalAPI 状态",
    "group_rank": "更新群排名",
    "群排名": "更新群排名",
    "test": "测试指令",
    "markdown_test": "测试 Markdown 消息",
}


def _prioritize_commands(commands: list[tuple[str, str, bool]]) -> list[tuple[str, str, bool]]:
    featured = [item for item in commands if item[0].removeprefix("/") in PANEL_FEATURED_COMMANDS]
    return featured + [item for item in commands if item not in featured]


def collect_commands() -> list[tuple[str, str, bool]]:
    """Collect project commands, keeping command names ahead of aliases."""
    from ..application.catalog import COMMANDS
    return _prioritize_commands([
        (f"/{spec.name}", spec.zh, False)
        for spec in COMMANDS if not spec.admin and spec.name not in PANEL_EXCLUDED_COMMANDS
    ])[:PANEL_ITEM_LIMIT]


async def _request(bot: Bot, method: str, path: str, **kwargs: Any) -> Any:
    request = Request(
        method,
        bot.adapter.get_api_base().joinpath(path),
        headers=await bot.get_authorization_header(),
        **kwargs,
    )
    response = await bot.adapter.request(request)
    if not 200 <= response.status_code < 300:
        detail = response.content.decode("utf-8", errors="replace") if isinstance(response.content, bytes) else response.content
        raise RuntimeError(f"QQ API {method} {path} failed: HTTP {response.status_code}: {detail}")
    return json.loads(response.content) if response.content else {}


def _panel_payload(items: list[tuple[str, str, bool]], index: int) -> dict[str, Any]:
    return {
        "items": [
            {"type": "command", "name": name, "desc": description, "only_admin": only_admin}
            for name, description, only_admin in items
        ],
        "remark": f"{PANEL_REMARK_PREFIX} {index}",
    }


async def sync_command_panels(bot: Bot) -> None:
    commands = collect_commands()
    if not commands:
        logger.warning("No GOKZ commands found; QQ command-panel sync skipped")
        return

    for scope in PANEL_SCOPES:
        existing = await _request(bot, "GET", "v2/panels", params={"scope": scope, "limit": 50})
        panels_by_remark = {
            record.get("panel", {}).get("remark"): record
            for record in existing.get("records", [])
            if record.get("panel", {}).get("remark", "").startswith(PANEL_REMARK_PREFIX)
        }

        # QQ's client renders one panel per conversation. Remove panels from
        # previous versions of this sync before publishing the single panel.
        for remark, record in panels_by_remark.items():
            if remark == f"{PANEL_REMARK_PREFIX} 1":
                continue
            try:
                await _request(bot, "DELETE", f"v2/panels/{record['panel_id']}")
            except RuntimeError as error:
                if "40030006" not in str(error):
                    raise

        panel = _panel_payload(commands, 1)
        previous = panels_by_remark.get(panel["remark"])
        if previous:
            # QQ returns the current revision on the record. Supplying it
            # avoids a stale-write rejection when a panel already exists.
            panel["version"] = previous.get("version")
            try:
                await _request(bot, "PUT", f"v2/panels/{previous['panel_id']}", json={"panel": panel})
                logger.info(f"Synced {len(commands)} commands to QQ {scope} command panel")
                continue
            except RuntimeError as error:
                # The list endpoint can briefly return a stale record after a
                # panel is removed. Recreate it instead of failing startup.
                if "40030006" not in str(error):
                    raise
                logger.warning(f"QQ command panel {previous['panel_id']} no longer exists; recreating it")

        panel.pop("version", None)
        await _request(
            bot,
            "POST",
            "v2/panels",
            json={"scope": scope, "target_type": "all", "panel": panel},
        )

        logger.info(f"Synced {len(commands)} commands to QQ {scope} command panel")


@get_driver().on_bot_connect
async def _sync_panels_on_connect(bot: Bot) -> None:
    if not isinstance(bot, Bot):
        return
    try:
        await sync_command_panels(bot)
    except Exception:
        logger.exception("Failed to synchronise QQ command panels")
