"""GOKZ command behavior shared by every transport."""

from __future__ import annotations

import asyncio
import os
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import nonebot_plugin_localstore as store
from sqlmodel import Session, col, select

from ..api.global_status import check_global_api
from ..api.gokz_top import (
    GOKZTopAPIError,
    fetch_personal_bans,
    fetch_personal_best,
    fetch_personal_recent,
    fetch_run_history,
    fetch_world_record,
)
from ..api.helper import fetch_json, put_json
from ..config import QQ_BOT_SECRET
from ..core.binding_code import verify_binding_code
from ..core.daily_map import get_daily_maps, get_maps, utc_today
from ..core.kreedz import format_kzmode
from ..core.kz.player_card import player_card_screenshot_async, website_base_url
from ..core.map_lookup import resolve_map_name
from ..core.server_status import resolve_server_group_slug
from ..core.steam_user import convert_steamid
from ..db.db import engine
from ..db.models import GroupServerSetting, PlatformPreference, User
from .catalog import COMMANDS
from .context import RequestContext
from .links import FEEDBACK_GROUP_URL
from .models import CommandInput, Result, UserError

BASE = os.getenv("GOKZ_TOP_API_URL", "https://api.gokz.top/v1").rstrip("/")


def text(ctx: RequestContext, en: str, zh: str) -> str:
    return en if ctx.platform == "discord" else zh


def preference(ctx: RequestContext, mode: str | None = None) -> str:
    with Session(engine) as session:
        if ctx.platform == "qq":
            row = session.get(User, ctx.account_id)
        else:
            row = session.get(PlatformPreference, ctx.storage_key)
            if row is None:
                row = PlatformPreference(account_key=ctx.storage_key)
        value = str(format_kzmode(mode or (row.mode if row else "OVR"), "m")).upper()
        if mode and row:
            row.mode = value
            session.add(row)
            session.commit()
        return value


async def binding(ctx: RequestContext, account: str | None = None) -> str | None:
    account = account or ctx.account_id
    if ctx.platform == "discord":
        with Session(engine) as session:
            row = session.get(PlatformPreference, f"discord:{account}")
            return row.steamid if row else None
    with Session(engine) as session:
        row = session.get(User, account)
        return convert_steamid(row.steamid, 64) if row else None


async def player(
    ctx: RequestContext, request: CommandInput, *, own: bool = False
) -> str:
    if not own and request.steamid:
        try:
            return convert_steamid(request.steamid, 64)
        except (ValueError, TypeError):
            raise UserError("Invalid Steam ID.", "Steam ID 格式不正确。")
    steamid = await binding(ctx, None if own else request.user)
    if steamid is None:
        raise UserError(
            "Connect your account with /bind first.", "请先使用 /bind 绑定账号。"
        )
    return steamid


async def read(path: str, **params: Any) -> Any:
    data = await fetch_json(f"{BASE}{path}", params=params or None, timeout=30)
    if data is None or isinstance(data, dict) and data.get("detail"):
        if (
            isinstance(data, dict)
            and isinstance(data.get("detail"), str)
            and "not found" in data["detail"].casefold()
        ):
            raise UserError(
                "No matching player or resource was found.", "未找到对应的玩家或资源。"
            )
        raise UserError(
            "GOKZ.TOP is temporarily unavailable. Please try again.",
            "GOKZ.TOP 暂时不可用，请稍后重试。",
            tone="error",
        )
    return data


async def map_result(
    ctx: RequestContext, name: str, request: CommandInput
) -> str | Result:
    if not request.arguments:
        raise UserError("Please provide a map name.", "请输入地图名。")
    try:
        await get_maps(request.mode or "KZT")
    except Exception:
        # Continue with the persisted/bundled catalog if refresh fails.
        pass
    map_name, choices = resolve_map_name(request.arguments[0])
    if choices:
        return Result(
            text(ctx, "Choose a map", "请选择地图"),
            choices=[
                (
                    candidate,
                    name,
                    replace(request, arguments=(candidate, *request.arguments[1:])),
                )
                for candidate in choices
            ],
        )
    if not map_name:
        raise UserError("Map not found.", "未找到该地图。")
    return map_name


def add_fields(
    result: Result,
    data: dict[str, Any],
    labels: tuple[tuple[str, str, str], ...],
    ctx: RequestContext,
) -> None:
    for key, en, zh in labels:
        if data.get(key) is not None:
            result.fields.append((text(ctx, en, zh), str(data[key])))


def record_result(
    ctx: RequestContext,
    title: str,
    records: list[tuple[str, dict[str, Any] | None]],
    scope: str,
) -> Result:
    result = Result(
        title,
        data={"records": dict(records), "map_name": title, "scope": scope},
        category="records",
        entries=[{"kind": kind, **record} for kind, record in records if record],
    )
    if records and any(record for _, record in records):
        result.image = f"{BASE}/maps/images/{quote(title, safe='')}.webp"
        result.links = [
            (
                text(ctx, "Map leaderboard", "地图排名"),
                f"{website_base_url()}/maps/{quote(title, safe='')}/maptop",
            )
        ]
    for kind, record in records:
        if not record:
            continue
        player_data = record.get("player") or {}
        seconds = float(record["time"])
        mins, secs = divmod(seconds, 60)
        value = f"{int(mins)}:{secs:06.3f} · {record.get('teleports', 0)} TP"
        value += f"\n{player_data.get('display_name') or record.get('player_name') or record.get('steam_id') or ''}"
        value += f"\n{record.get('mode', scope)} · T{record.get('map_tier', '?')}"
        if record.get("rating") is not None:
            value += f"\n{text(ctx, 'Rating', '评分')}: {record['rating']}"
        if record.get("server_name"):
            value += f"\n{record['server_name']}"
        if record.get("created_on"):
            value += f"\n{record['created_on']}"
        result.fields.append((kind, value))
    if not result.fields:
        result.description = text(ctx, "No records found.", "未找到记录。")
    return result


async def execute(ctx: RequestContext, name: str, request: CommandInput) -> Result:
    """The single feature entrypoint used by both adapter integrations."""
    try:
        return await _execute(ctx, name, request)
    except GOKZTopAPIError as exc:
        raise UserError(
            "GOKZ.TOP is temporarily unavailable. Please try again.",
            "GOKZ.TOP API服务暂时不可用，请稍后再试。",
            tone="error",
        ) from exc


async def _execute(ctx: RequestContext, name: str, request: CommandInput) -> Result:
    if name in {"set_server", "group_rank"} and not ctx.is_admin:
        raise UserError(
            "This command is restricted to bot administrators.",
            "该命令仅限机器人管理员使用。",
        )
    if name == "help":
        return Result(
            text(ctx, "GOKZ commands", "GOKZ 指令"),
            "\n".join(
                f"/{s.name} — {s.en if ctx.platform == 'discord' else s.zh}"
                for s in COMMANDS
                if not s.admin or ctx.is_admin
            ),
        )
    if name == "feedback":
        return Result(
            text(ctx, "Feedback", "问题反馈"),
            links=[
                ("GOKZ.TOP", website_base_url()),
                (
                    text(ctx, "Support group", "反馈群"),
                    FEEDBACK_GROUP_URL,
                ),
            ],
        )
    if name == "bind":
        if not request.arguments:
            return Result(
                text(ctx, "Connect your Steam account", "绑定 Steam 账号"),
                text(
                    ctx,
                    "Sign in with Steam on GOKZ.TOP, generate a binding code, then run /bind code:KZTOP… . Codes are case-sensitive and expire quickly.",
                    "在网站登录 Steam 并生成绑定码，然后发送 /bind KZTOP…",
                ),
                links=[
                    (
                        text(ctx, "Generate binding code", "生成绑定码"),
                        f"{website_base_url()}/settings/binding-code",
                    )
                ],
                private=True,
            )
        if not QQ_BOT_SECRET:
            raise UserError(
                "Binding is not configured. Contact the bot administrator.",
                "绑定码功能未配置，请联系管理员",
            )
        try:
            steamid = verify_binding_code(request.arguments[0], QQ_BOT_SECRET)[
                "steamid64"
            ]
        except ValueError:
            raise UserError(
                "Invalid or expired binding code.", "绑定码无效或已过期，请重新生成"
            )
        data = await read(f"/players/{steamid}")
        if not isinstance(data, dict) or not data.get("name"):
            raise UserError(
                "No GOKZ player was found for this account. Complete a GOKZ map first.",
                "用户不存在. 你至少上传过一次GOKZ记录吗?\n(最近才入坑的玩家绑不上是正常的)",
            )
        with Session(engine) as session:
            if ctx.platform == "discord":
                # Transfer only within Discord; QQ bindings are independent.
                for old in session.exec(
                    select(PlatformPreference).where(
                        PlatformPreference.steamid == steamid
                    )
                ).all():
                    if old.account_key != ctx.storage_key:
                        old.steamid = None
                        session.add(old)
                row = session.get(
                    PlatformPreference, ctx.storage_key
                ) or PlatformPreference(account_key=ctx.storage_key)
                row.steamid = steamid
            else:
                for old in session.exec(
                    select(User).where(User.steamid == steamid)
                ).all():
                    if old.qid != ctx.account_id:
                        session.delete(old)
                row = session.get(User, ctx.account_id) or User(
                    qid=ctx.account_id, name="", steamid=steamid
                )
                row.steamid, row.name = steamid, data.get("name") or steamid
            session.add(row)
            session.commit()
        return Result(
            text(ctx, "Account connected", "绑定成功"),
            f"{data.get('name') or steamid}\n{steamid}",
            private=True,
            data={"name": data.get("name") or steamid, "steamid": steamid},
        )
    if name == "api":
        status = await check_global_api()
        return Result(
            "GlobalAPI",
            text(
                ctx,
                "Available" if status.available else "Unavailable",
                "可用" if status.available else "不可用",
            ),
            fields=[
                (text(ctx, "Response time", "响应时间"), f"{status.response_ms:.0f} ms")
            ]
            + (
                [
                    (
                        text(ctx, "Details", "详情"),
                        (
                            "Request timed out after 10 seconds."
                            if "超时" in status.error
                            else "The API returned an invalid response."
                            if "无效" in status.error
                            else "Unable to connect to the API."
                            if "网络" in status.error
                            else status.error
                        )
                        if ctx.platform == "discord"
                        else status.error,
                    )
                ]
                if status.error
                else []
            ),
            tone="success" if status.available else "error",
            data={"status": status},
        )
    if name in {"server", "group_info", "set_server"}:
        return await servers(ctx, name, request)
    if name == "find":
        query = " ".join(request.arguments)
        if not query:
            raise UserError("Please provide a player name.", "请输入玩家名。")
        data = await read("/players/search", q=query, limit=10)
        return Result(
            text(ctx, "Player search", "查找玩家"),
            "\n".join(
                f"{p.get('alias') or p.get('name')} · {p['steamid64']}"
                for p in data.get("data", [])
            )
            or text(ctx, "No players found.", "未找到玩家。"),
            data={"players": data.get("data", [])},
        )
    if name == "group_rank":
        with Session(engine) as session:
            users = (
                session.exec(select(User)).all()[:20]
                if ctx.platform == "qq"
                else session.exec(
                    select(PlatformPreference).where(
                        col(PlatformPreference.steamid).is_not(None)
                    )
                ).all()[:20]
            )
        rows = await asyncio.gather(
            *(read(f"/leaderboards/players/{u.steamid}", scope="OVR") for u in users)
        )
        return Result(
            text(ctx, "Linked player rankings", "已绑定玩家排名"),
            "\n".join(
                f"{getattr(u, 'name', None) or u.steamid}: {r.get('rank', '—')}"
                for u, r in sorted(
                    zip(users, rows), key=lambda pair: pair[1].get("rank") or 10**9
                )
            ),
        )
    if name == "mode":
        await player(ctx, request, own=True)
        chosen = request.arguments[0] if request.arguments else request.mode
        try:
            scope = preference(ctx, chosen)
        except ValueError:
            raise UserError("Choose OVR, KZT, SKZ, or VNL.", "模式格式不正确")
        return Result(
            text(ctx, "Default mode", "默认模式"),
            scope,
            data={"scope": scope},
            choices=[
                (m, "mode", CommandInput(arguments=(m,)))
                for m in ("OVR", "KZT", "SKZ", "VNL")
            ],
        )
    try:
        scope = str(format_kzmode(request.mode or preference(ctx), "m")).upper()
    except ValueError:
        raise UserError(
            "Invalid mode. Choose OVR, KZT, SKZ, or VNL.", "模式格式不正确。"
        )
    request = replace(request, mode=scope)
    # Public WR/review queries do not require an account binding.
    steamid = (
        None
        if name in {"wr", "review"}
        else await player(ctx, request, own=name in {"rate", "comment", "pk"})
    )
    if name in {"info", "profile", "kz"}:
        if name == "info":
            with Session(engine) as session:
                account = (
                    session.get(User, request.user or ctx.account_id)
                    if ctx.platform == "qq"
                    else None
                )
                account_name = account.name if account else steamid
            return Result(
                text(ctx, "Linked account", "绑定信息"),
                fields=[("Steam ID", steamid), (text(ctx, "Mode", "模式"), scope)],
                data={"account_name": account_name, "steamid": steamid, "scope": scope},
            )
        data = await read(f"/players/{steamid}")
        if not isinstance(data, dict) or not data.get("steamid64"):
            raise UserError(
                "No GOKZ player profile was found.",
                "未找到 GOKZ.TOP 玩家资料，或 API 暂时不可用，请稍后再试。",
            )
        title = data.get("alias") or data.get("name") or steamid
        result = Result(
            title,
            links=[
                ("GOKZ.TOP", f"{website_base_url()}/profile/{steamid}"),
                ("Steam", f"https://steamcommunity.com/profiles/{steamid}"),
            ],
        )
        result.fields = [("Steam ID", steamid), (text(ctx, "Mode", "模式"), scope)]
        result.data = {"player": data, "steamid": steamid, "scope": scope}
        if name == "profile":
            optional = await asyncio.gather(
                read(f"/player-social-links/players/{steamid}"),
                read(f"/players/{steamid}/stats"),
                read(f"/leaderboards/players/{steamid}", scope=scope),
                read(
                    f"/players/{steamid}/jumpstats",
                    type="LJ",
                    limit=1,
                    sort_by="distance",
                    sort_order="desc",
                ),
                read(f"/players/{steamid}/tournament-achievements"),
                return_exceptions=True,
            )
            links_data, stats, rank, jumpstats, achievements = [
                value if isinstance(value, dict) else {} for value in optional
            ]
            for collection in (links_data, jumpstats, achievements):
                if not isinstance(collection.get("data"), list):
                    collection["data"] = []
            result.data.update(
                links=links_data.get("data", []),
                stats=stats,
                rank=rank,
                jumpstats=jumpstats,
                achievements=achievements,
            )
            for link in links_data.get("data", []):
                if link.get("verified") and link.get("url"):
                    result.links.append(
                        (str(link.get("platform", "Profile")), link["url"])
                    )
            result.category = "profile"
            result.entries = [
                {"player": data, "stats": stats, "rank": rank, "scope": scope}
            ]
            add_fields(
                result,
                rank,
                (
                    ("rank", "Rank", "排名"),
                    ("rating", "Rating", "评分"),
                    ("unique_map_finishes", "Maps finished", "完成地图数"),
                ),
                ctx,
            )
            if any(isinstance(value, Exception) for value in optional):
                result.tone = "warning"
                result.footer = text(
                    ctx,
                    "Some profile details are temporarily unavailable.",
                    "部分资料暂时不可用。",
                )
        if name == "kz":
            try:
                result.file = Path(
                    await player_card_screenshot_async(
                        steamid,
                        scope,
                        store.get_cache_dir("player_cards"),
                        request.update,
                        ctx.locale,
                    )
                )
            except Exception as exc:
                raise UserError(
                    f"Card generation failed. View your profile: {website_base_url()}/profile/{steamid}",
                    f"玩家卡片生成失败，可直接查看资料：\n{website_base_url()}/profile/{steamid}",
                ) from exc
        return result
    if name in {"pb", "wr", "mp", "review", "rate", "comment"}:
        selected = await map_result(ctx, name, request)
        if isinstance(selected, Result):
            return selected
        map_name = selected
        if name in {"pb", "wr"}:
            records = await asyncio.gather(
                *(
                    fetch_personal_best(steamid, map_name, scope, t)
                    if name == "pb"
                    else fetch_world_record(map_name, scope, t)
                    for t in ("NUB", "PRO")
                )
            )
            result = record_result(
                ctx, map_name, list(zip(("NUB", "PRO"), records)), scope
            )
            result.links = [
                (
                    text(ctx, "Map leaderboard", "地图排名"),
                    f"{website_base_url()}/maps/{quote(map_name)}/maptop",
                )
            ]
            result.image = f"{BASE}/maps/images/{quote(map_name)}.webp"
            return result
        maps = await read("/maps", name=map_name, limit=10)
        map_data = next((m for m in maps if m["name"] == map_name), None)
        if map_data is None:
            raise UserError("Map not found.", "未找到地图。")
        if name == "mp":
            histories = await asyncio.gather(
                *(
                    fetch_run_history(steamid, map_data["id"], scope, t)
                    for t in ("NUB", "PRO")
                ),
                return_exceptions=True,
            )
            if all(isinstance(h, Exception) for h in histories):
                raise UserError(
                    "Run history is unavailable.",
                    "GOKZ.TOP API服务暂时不可用，请稍后再试。",
                    tone="error",
                )
            progress = {}
            result = Result(
                map_name,
                data={"map_name": map_name, "scope": scope, "steamid": steamid},
            )
            for kind, history in zip(("NUB", "PRO"), histories):
                records = history.get("data", []) if isinstance(history, dict) else []
                records = [
                    r for r in records if (r.get("teleports", 0) > 0) == (kind == "NUB")
                ]
                bests = personal_bests(records)
                progress[kind] = bests
                result.fields.append(
                    (
                        kind,
                        "\n".join(
                            f"{r['time']:.3f}s · {r['created_on']}"
                            for r, _ in reversed(bests[:10])
                        )
                        or "—",
                    )
                )
            result.data["progress"] = progress
            return result
        return await reviews(ctx, name, request, map_data, steamid)
    if name == "pr":
        record = await fetch_personal_recent(steamid, scope)
        result = record_result(
            ctx,
            record.get("map_name", "PR") if record else "PR",
            [("PR", record)],
            scope,
        )
        result.record = record
        return result
    if name == "ban":
        rows = await fetch_personal_bans(steamid)
        return Result(
            text(ctx, "Ban history", "封禁记录"),
            text(ctx, "No bans found.", "未找到封禁记录。") if not rows else "",
            fields=[
                (
                    str(r.get("ban_type", "other")).replace("_", " "),
                    str(r.get("notes") or r.get("reason") or "—"),
                )
                for r in rows[:5]
            ],
            category="bans",
            entries=rows[:5],
            data={"bans": rows, "steamid": steamid},
            footer=text(
                ctx,
                f"{len(rows)} records · showing {min(5, len(rows))}",
                f"共 {len(rows)} 条 · 显示 {min(5, len(rows))} 条",
            ),
            tone="success" if not rows else "error",
        )
    if name in {"rank", "pk"}:
        if request.update:
            await put_json(f"{BASE}/leaderboards/players/{steamid}", timeout=30)
        rank = await read(f"/leaderboards/players/{steamid}", scope=scope)
        result = Result(text(ctx, "Player rankings", "玩家排名"))
        keys = (
            ("rank", "Rank", "排名"),
            ("rank_regional", "Regional rank", "地区排名"),
            ("rating", "Rating", "评分"),
            ("nub_rating", "NUB rating", "NUB 评分"),
            ("pro_rating", "PRO rating", "PRO 评分"),
            ("unique_map_finishes", "Maps finished", "完成地图数"),
        )
        add_fields(result, rank, keys, ctx)
        if name == "rank":
            try:
                profile = await read(f"/players/{steamid}")
            except UserError:
                profile = rank.get("player") or {"steamid64": steamid}
            result.data = {
                "player": profile,
                "rank": rank,
                "scope": scope,
                "steamid": steamid,
            }
            result.category = "rank"
            result.entries = [{"player": profile, "rank": rank, "scope": scope}]
            result.links = [
                ("GOKZ.TOP", f"{website_base_url()}/profile/{steamid}"),
                ("Steam", f"https://steamcommunity.com/profiles/{steamid}"),
            ]

        if name == "pk":
            opponent = request.arguments[0] if request.arguments else request.steamid
            if request.user:
                opponent = await binding(ctx, request.user)
            if not opponent:
                raise UserError(
                    "Select an opponent or provide their Steam ID.",
                    "请指定对手或提供 Steam ID。",
                )
            other = await read(
                f"/leaderboards/players/{convert_steamid(opponent, 64)}", scope=scope
            )
            result.fields = [
                (text(ctx, en, zh), f"{rank.get(k, '—')} / {other.get(k, '—')}")
                for k, en, zh in keys
            ]
        return result
    if name == "daily":
        assignments = await get_daily_maps(
            ctx.account_id if ctx.platform == "qq" else ctx.storage_key, steamid, scope
        )
        if assignments is None:
            raise UserError(
                "Daily maps are temporarily unavailable.", "每日地图暂时不可用。"
            )
        return Result(
            text(ctx, "Daily maps", "每日地图"),
            str(utc_today()),
            data={"assignments": assignments, "date": utc_today()},
            fields=[
                (
                    text(ctx, en, zh),
                    f"{assignments[k].map_name} · T{assignments[k].map_tier}"
                    if assignments.get(k)
                    else "—",
                )
                for k, en, zh in (
                    ("new", "New map", "开荒新图"),
                    ("improvement", "Improve your PB", "挑战旧图"),
                )
            ],
        )
    if name == "ccf":
        data = await read(f"/players/{steamid}/stats")
        period = (request.arguments or ("all",))[0]
        if period not in {
            "all",
            "pb",
            "top",
            "last_year",
            "year",
            "last_100_hours",
            "100h",
        }:
            raise UserError(
                "Choose all, pb, last_year, or last_100_hours.",
                "请选择 all、pb、last_year 或 last_100_hours。",
            )
        # The v1 API currently provides server playtime for all time only.
        distribution = data.get("most_played_server") or {}
        all_time = distribution.get("all_time") or {}
        groups = all_time.get("entries") or []
        return Result(
            text(ctx, "Most-played servers (all time)", "常玩服务器（全部）"),
            "\n".join(
                f"{g.get('label', '—')}: {float(g.get('total_seconds', 0)) / 3600:.2f}h"
                for g in groups[:10]
            )
            or "—",
            data={
                "stats": data,
                "preset": {
                    "top": "pb",
                    "year": "last_year",
                    "100h": "last_100_hours",
                }.get(period, period),
            },
        )
    if name == "pw":
        data = await perfect_world(steamid, (request.arguments or ("S20",))[0])
        summary = perfect_world_summary(data)
        result = Result(
            "Perfect World",
            str(data.get("name", "")),
            data={"stats": data, "summary": summary},
        )
        add_fields(
            result,
            data,
            (
                ("pvpScore", "Score", "分数"),
                ("pwRating", "Rating", "Rating"),
                ("kd", "K/D", "K/D"),
                ("adr", "ADR", "ADR"),
                ("winRate", "Win rate", "胜率"),
            ),
            ctx,
        )
        result.fields.extend(
            [
                (text(ctx, "Rank", "段位"), summary["rank"]),
                (text(ctx, "Matches", "总场次"), str(summary["match_count"])),
                (
                    text(ctx, "Recent 5 rating", "最近5场Rating"),
                    f"{summary['ratings_avg']:.2f}",
                ),
            ]
        )
        return result
    raise UserError("Unknown command.", "未知指令。")


async def servers(ctx: RequestContext, name: str, request: CommandInput) -> Result:
    key = (
        ctx.conversation_id
        if ctx.platform == "qq"
        else f"discord:{ctx.conversation_id}"
    )
    with Session(engine) as session:
        setting = session.get(GroupServerSetting, key) if ctx.conversation_id else None
        default = setting.server_group if setting else ""
    if name == "group_info":
        return Result(
            text(ctx, "Conversation settings", "群组设置"),
            f"{ctx.conversation_id or '—'}\n{default or '—'}",
            data={"conversation_id": ctx.conversation_id, "default": default},
        )
    identifier = " ".join(request.arguments).strip() or default
    if name == "set_server":
        if not request.arguments or (
            not ctx.conversation_id and len(request.arguments) != 2
        ):
            raise UserError(
                "Use /set_server group in a server.",
                "请在群聊中使用 /set_server 服务器组。",
            )
        if len(request.arguments) == 2:
            target, identifier = request.arguments
            key = target if ctx.platform == "qq" else f"discord:{target}"
    data = await read("/servers", offset=0, limit=200)
    rows = data.get("data", [])
    slug = resolve_server_group_slug(rows, identifier) if identifier else None
    if name == "set_server":
        if not slug:
            raise UserError("Server group not found.", "未找到服务器组。")
        with Session(engine) as session:
            setting = session.get(GroupServerSetting, key) or GroupServerSetting(
                group_id=key, server_group=slug
            )
            setting.server_group = slug
            session.add(setting)
            session.commit()
        return Result(
            text(ctx, "Default server group updated", "默认服务器组已更新"),
            slug,
            data={"conversation_id": key.removeprefix("discord:"), "default": slug},
        )

    result = Result(
        text(ctx, "Live servers", "服务器状态"),
        category="servers",
        data={"servers": rows, "identifier": identifier, "slug": slug},
    )
    if identifier and not slug:
        result.tone = "warning"
    groups = {}
    for row in rows:
        group = row.get("group") or {}
        group_slug = group.get("custom_id")
        live = row.get("live_status") or {}
        if not group_slug or not live.get("is_online"):
            continue
        groups[group_slug] = group.get("name") or group_slug
        if slug == group_slug:
            result.entries.append(row)
            roster = " · ".join(
                str(p.get("name", "")) for p in live.get("players", [])[:15]
            )
            result.fields.append(
                (
                    str(live.get("hostname") or f"{row.get('ip')}:{row.get('port')}"),
                    f"{live.get('map', '—')} · {live.get('player_count', 0)}\n{roster}",
                )
            )
    if slug:
        result.title = groups.get(slug, slug)
        result.links = [
            (
                text(ctx, "Server group", "服务器组"),
                f"{website_base_url()}/servers/group/{quote(slug, safe='')}",
            )
        ]
        result.footer = text(
            ctx, f"{len(result.entries)} online servers", "在线服务器状态"
        )
        if not result.entries:
            result.tone = "warning"
            result.description = text(
                ctx, "No servers are currently online.", "当前没有在线服务器。"
            )
    if not slug:
        result.category = "server_groups"
        result.entries = [
            {
                "slug": key,
                "name": value,
                "servers": sum(
                    1
                    for row in rows
                    if (row.get("group") or {}).get("custom_id") == key
                    and (row.get("live_status") or {}).get("is_online")
                ),
                "players": sum(
                    int((row.get("live_status") or {}).get("player_count") or 0)
                    for row in rows
                    if (row.get("group") or {}).get("custom_id") == key
                    and (row.get("live_status") or {}).get("is_online")
                ),
            }
            for key, value in groups.items()
        ]
        if not groups:
            result.tone = "warning"
        result.description = "\n".join(f"{v} (`{k}`)" for k, v in groups.items()) or "—"
        result.choices = [
            (v, "server", CommandInput(arguments=(k,)))
            for k, v in list(groups.items())[:20]
        ]
    return result


async def reviews(
    ctx: RequestContext,
    name: str,
    request: CommandInput,
    map_data: dict[str, Any],
    steamid: str | None,
) -> Result:
    map_id = map_data["id"]
    map_name = map_data["name"]
    rows = await read(
        "/maps/reviews",
        map_id=map_id,
        limit=100,
        **({"steamid64": steamid} if name in {"comment", "rate"} else {}),
    )
    if name == "review":
        ratings = [r.get("content") or {} for r in rows.get("data", [])]
        summary = {}
        for aspect in ("overall", "visuals", "gameplay"):
            values = [r[aspect] for r in ratings if r.get(aspect) is not None]
            summary[aspect] = (
                (sum(values) / len(values), len(values)) if values else (0, 0)
            )
        comments = await read(
            "/maps/reviews",
            map_id=map_id,
            offset=0,
            limit=100,
            with_comments_only="true",
        )
        result = Result(
            map_name,
            data={
                "map": map_data,
                "ratings": ratings,
                "summary": summary,
                "comments": comments,
                "comment_count": sum(bool(r.get("comment")) for r in ratings),
            },
        )
        for r in comments.get("data", [])[:5]:
            content = r.get("content") or {}
            comment = content.get("comment") or {}
            result.fields.append(
                (
                    str((r.get("player") or {}).get("display_name", "—")),
                    f"{content.get('overall', '—')} ★\n{comment.get('text', '') if isinstance(comment, dict) else comment}",
                )
            )
        return result
    if name == "rate":
        stars = request.overall
        trailing = list(request.arguments[1:])
        if stars is None and trailing:
            try:
                stars = int(trailing.pop(0))
            except ValueError:
                raise UserError(
                    "The overall rating must be between 1 and 5.",
                    "总体评分必须为 1–5。",
                )
        if stars is None:
            return Result(
                map_name,
                data={
                    "map_name": map_name,
                    "current_rating": next(iter(rows.get("data", [])), {})
                    .get("content", {})
                    .get("overall"),
                },
                choices=[
                    (f"{n} ★", "rate", replace(request, overall=n)) for n in range(1, 6)
                ],
            )
        content = {
            "overall": stars,
            "gameplay": request.gameplay,
            "visuals": request.visuals,
        }
        if len(trailing) >= 2 and all(t.isdigit() for t in trailing[:2]):
            content.update(gameplay=int(trailing.pop(0)), visuals=int(trailing.pop(0)))
        comment = request.comment or " ".join(trailing)
        if comment:
            content["comment"] = {"text": comment}
    else:
        existing = next(iter(rows.get("data", [])), {}).get("content") or {}
        if not existing.get("overall"):
            raise UserError(
                "Rate this map with /rate before adding a comment.",
                "请先使用 /rate 评分，再添加评论。",
            )
        content = dict(existing)
        comment = request.comment or " ".join(request.arguments[1:])
        if not comment:
            raise UserError("Please provide a comment.", "请输入评论。")
        content["comment"] = {
            **(
                existing.get("comment")
                if isinstance(existing.get("comment"), dict)
                else {}
            ),
            "text": comment,
        }
    if any(
        not isinstance(v, int) or not 1 <= v <= 5
        for k, v in content.items()
        if k != "comment" and v is not None
    ):
        raise UserError("Ratings must be between 1 and 5.", "评分必须为 1–5。")
    if len((content.get("comment") or {}).get("text", "")) > 1000:
        raise UserError(
            "Comments must be at most 1,000 characters.", "评论最多 1000 个字符。"
        )
    payload = {"map_id": map_id, "content": content}
    # Both official adapters verify website-issued binding codes locally.
    payload["steamid64"] = steamid
    url = f"{BASE}/maps/reviews"
    headers = {"X-QQ-Bot-Key": QQ_BOT_SECRET}
    result = await put_json(url, json_data=payload, headers=headers, timeout=30)
    if not isinstance(result, dict) or result.get("detail"):
        raise UserError(
            "Unable to save your review. Check that you have completed this map.",
            "无法保存评价，请确认已完成该地图。",
        )
    return Result(
        text(ctx, "Review saved", "评价已保存"),
        map_name,
        data={"map_name": map_name, "content": content, "saved": True},
    )


def personal_bests(records: list[dict[str, Any]]) -> list[tuple[dict[str, Any], int]]:
    """Newest PB first, retaining completions between improvements."""
    bests = []
    completions = 0
    best = None
    for record in sorted(records, key=lambda r: r["created_on"]):
        if best is None or record["time"] < best:
            bests.append((record, completions))
            best = record["time"]
            completions = 0
        else:
            completions += 1
    return list(reversed(bests))


async def perfect_world(steamid: str, season: str) -> dict[str, Any]:
    season = season.upper() if season.upper().startswith("S") else "S20"
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://api.wmpvp.com/api/v2/csgo/pvpDetailDataStats",
            json={"steamId64": steamid, "csgoSeasonId": season},
            headers={
                "User-Agent": "okhttp/4.11.0",
                "t": str(int(__import__("time").time())),
            },
        )
        response.raise_for_status()
        body = response.json()
    data = body.get("data")
    if body.get("statusCode", 0) != 0 or not isinstance(data, dict):
        raise UserError(
            "Perfect World statistics are unavailable.",
            "获取数据失败，请检查SteamID是否正确",
        )
    return data


def perfect_world_summary(data: dict[str, Any]) -> dict[str, Any]:
    history = data.get("historyPwRatings", [])
    ratings = history[:5]
    score = data.get("pvpScore", 0)
    bands = (
        (1000, "D"),
        (1200, "D+"),
        (1400, "C"),
        (1600, "C+"),
        (1800, "B"),
        (2000, "B+"),
        (2200, "A"),
        (2400, "A+"),
    )
    return {
        "score": score,
        "ratings": ratings,
        "match_count": len(history),
        "rank": next((label for maximum, label in bands if score <= maximum), "S"),
        "ratings_avg": sum(ratings) / len(ratings) if ratings else 0,
    }
