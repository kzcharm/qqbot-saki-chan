"""Synchronise the QQ command panel with this plugin's NoneBot commands."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any

from nonebot import get_driver, logger
from nonebot.adapters.qq import Bot
from nonebot.drivers import Request
from nonebot.matcher import matchers
from nonebot.rule import CommandRule


PANEL_REMARK_PREFIX = "gokz-qqbot commands"
PANEL_ITEM_LIMIT = 20
PANEL_SCOPES = ("c2c", "group")
PANEL_EXCLUDED_COMMANDS = {"test", "markdown_test"}
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
    "kz": "生成 kzgo.eu 截图",
    "pb": "查询地图个人最佳",
    "pr": "查询最近跳图记录",
    "wr": "查询地图世界记录",
    "rank": "查询 gokz.top 排名",
    "pk": "与他人进行 Rank PK",
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


def _command_names(matcher: type[Any]) -> tuple[str, ...]:
    """Return a matcher's main command followed by its aliases."""
    for checker in matcher.rule.checkers:
        rule = checker.call
        if isinstance(rule, CommandRule):
            commands = [".".join(command) for command in rule.cmds]
            # ``CommandRule.cmds`` stores aliases in a set-derived order.
            # The first registered command is available from the Trie rule, so
            # sort here for deterministic panels; primary names are promoted
            # below using their explicit registration order when possible.
            return tuple(sorted(commands, key=lambda name: (not name.isascii(), name)))
    return ()


def _primary_command(matcher: type[Any], names: tuple[str, ...]) -> str:
    """Recover ``on_command``'s first argument from its source declaration."""
    source = matcher._source
    module = source and sys.modules.get(source.module_name)
    source_file = module and getattr(module, "__file__", None)
    if not source_file or not source:
        return names[0]

    try:
        tree = ast.parse(Path(source_file).read_text(encoding="utf-8"), filename=source_file)
    except OSError:
        return names[0]

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or node.lineno != source.lineno:
            continue
        if not isinstance(node.value, ast.Call) or not node.value.args:
            continue
        if getattr(node.value.func, "id", None) != "on_command":
            continue
        first_arg = node.value.args[0]
        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
            if first_arg.value in names:
                return first_arg.value
    return names[0]


def _prioritize_commands(commands: list[tuple[str, str, bool]]) -> list[tuple[str, str, bool]]:
    featured = [item for item in commands if item[0].removeprefix("/") in PANEL_FEATURED_COMMANDS]
    return featured + [item for item in commands if item not in featured]


def collect_commands() -> list[tuple[str, str, bool]]:
    """Collect project commands, keeping command names ahead of aliases."""
    primary: list[tuple[str, str, bool]] = []
    aliases: list[tuple[str, str, bool]] = []
    seen: set[str] = set()

    for priority in sorted(matchers):
        for matcher in matchers[priority]:
            if not matcher.module_name.startswith("src.plugins.gokz.plugins."):
                continue
            names = _command_names(matcher)
            if not names:
                continue

            canonical = _primary_command(matcher, names)
            description = COMMAND_DESCRIPTIONS.get(canonical, "执行机器人指令")
            only_admin = bool(matcher.permission.checkers)
            if only_admin or canonical in PANEL_EXCLUDED_COMMANDS:
                continue

            for target, bucket in ((canonical, primary), *[(name, aliases) for name in names if name != canonical]):
                panel_name = f"/{target}"
                if panel_name in seen or len(panel_name) > 14:
                    continue
                seen.add(panel_name)
                bucket.append((panel_name, description, only_admin))

    return _prioritize_commands(primary + aliases)[:PANEL_ITEM_LIMIT]


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
    try:
        await sync_command_panels(bot)
    except Exception:
        logger.exception("Failed to synchronise QQ command panels")
