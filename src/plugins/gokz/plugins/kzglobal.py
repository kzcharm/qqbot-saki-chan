import asyncio
import math
from datetime import datetime
from pathlib import Path
from textwrap import dedent
from urllib.parse import quote
from zoneinfo import ZoneInfo

from nonebot import get_driver, logger
from nonebot.adapters.qq import Bot, Event, Message, MessageSegment
from nonebot.adapters.qq.models import MessageMarkdown
from nonebot.exception import FinishedException
from nonebot.params import CommandArg
from src.plugins.gokz.core.command_helper import CommandData
from src.plugins.gokz.core.config import MAP_TIERS
from src.plugins.gokz.core.formatter import format_gruntime, record_format_time
from src.plugins.gokz.core.keyboard import KeyboardBuilder
from src.plugins.gokz.core.kreedz import format_kzmode
from src.plugins.gokz.core.map_selection import (
    map_command,
)
from src.plugins.gokz.core.pr_compliment import (
    is_notable_run,
    maybe_send_pr_compliment,
)
from src.plugins.gokz.core.rate_message import rate_selection_message

from ..api.gokz_top import (
    GOKZTopAPIError,
)
from ..application.models import CommandInput
from ..config import environment
from ..presentation.qq_bridge import command_input, query
from ..presentation.qq_legacy import on_command

pb = on_command('pb', aliases={'personal-best'})
pr = on_command('pr')
kz = on_command('kz', aliases={'kzgo'})
wr = on_command('wr')
ban_ = on_command('ban')
rank = on_command('rank')
review = on_command('review', aliases={'评价', '评论'})
rate = on_command('rate', aliases={'评分', '评价地图'})
comment = on_command('comment', aliases={'地图评论'})

private_map_names: dict[int, str] = {}  # For private messages
group_map_names: dict[int, str] = {}  # For group messages

DEFAULT_MAP = 'bkz_cakewalk'
GOKZ_TOP_V1 = "https://api.gokz.top/v1"
GOKZ_TOP_UNAVAILABLE = "GOKZ.TOP API服务暂时不可用，请稍后再试。"
PR_IMAGE_BASE_URL = "https://gokztop-1312466598.cos.ap-guangzhou.myqcloud.com/map-images"


def is_dev_superuser(event: Event) -> bool:
    """Allow repeatable voice tests without weakening production safeguards."""
    return (
        environment.lower() == "dev"
        and event.get_user_id() in get_driver().config.superusers
    )


def selected_gokz_command(command: str, map_name: str, cd: CommandData) -> str:
    """Recreate a GOKZ query after a user chooses an ambiguous map."""
    arguments = ("-m", str(format_kzmode(cd.mode, "m").upper()))
    if cd.steamid2:
        arguments += ("-s", cd.steamid)
    return map_command(command, map_name, *arguments)


def pb_action_keyboard(
    event: Event,
    cd: CommandData,
    map_name: str,
    include_other_modes: bool = True,
):
    """Build follow-up actions for a PB result.

    In group chats, anyone viewing the result can use the self-query action.
    Its command deliberately has no player target, so it resolves to the
    group member who taps it. ``enter=True`` submits it directly.
    """
    mode = f" -m {format_kzmode(cd.mode, 'm').upper()}" if cd.mode else ""
    target_arg = f" -s {cd.steamid}" if cd.steamid2 and cd.steamid != cd.steamid2 else ""
    current_mode = format_kzmode(cd.mode, "m")
    other_modes = [
        (label, value)
        for label, value in (("OVR", "OVR"), ("KZT", "KZT"), ("SKZ", "SKZ"), ("VNL", "VNL"))
        if value.lower() != current_mode
    ]
    actions = []
    # The QQ adapter identifies groups with ``group_openid``.  Keep
    # ``group_id`` as a fallback for compatible event implementations.
    is_group_chat = bool(
        getattr(event, "group_openid", None) or getattr(event, "group_id", None)
    )
    if is_group_chat:
        actions.append(
            KeyboardBuilder.button(
                id="pb_self",
                label="查询我的记录",
                visited_label="查询中",
                style=1,
                action_type=2,
                permission_type=2,
                action_data=f"/pb {map_name}{mode}",
                reply=True,
                enter=True,
            )
        )
    actions.append(
        KeyboardBuilder.button(
            id="pb_wr",
            label="查询WR",
            visited_label="查询中",
            style=1,
            action_type=2,
            permission_type=2,
            action_data=f"/wr {map_name}{mode}",
            reply=True,
            enter=True,
        )
    )
    actions.append(
        KeyboardBuilder.button(
            id="pb_leaderboard",
            label="排行榜",
            visited_label="打开中",
            style=1,
            action_type=0,
            permission_type=2,
            action_data=f"https://gokz.top/maps/{quote(map_name, safe='')}/maptop",
            reply=False,
            enter=False,
        )
    )
    actions.append(
        KeyboardBuilder.button(
            id="pb_progress",
            label="地图提升",
            visited_label="查询中",
            style=1,
            action_type=2,
            permission_type=2,
            action_data=f"/mp {map_name}{mode}{target_arg}",
            reply=True,
            enter=True,
        )
    )
    if include_other_modes:
        actions.extend(
            KeyboardBuilder.button(
                id=f"pb_{other_mode}",
                label=f"查询{label}",
                visited_label="查询中",
                style=1,
                action_type=2,
                permission_type=2,
                action_data=f"/pb {map_name} -m {other_mode}{target_arg}",
                reply=True,
                enter=True,
            )
            for label, other_mode in other_modes
        )
    actions.append(
        KeyboardBuilder.button(
            id="pb_rate",
            label="评分",
            visited_label="打开评分",
            style=1,
            action_type=2,
            permission_type=2,
            action_data=f"/rate {map_name}",
            reply=True,
            enter=True,
        )
    )
    if len(actions) >= 3 and len(actions) % 2:
        rows = [
            *(actions[index:index + 2] for index in range(0, len(actions) - 3, 2)),
            actions[-3:],
        ]
    else:
        rows = [actions[index:index + 2] for index in range(0, len(actions), 2)]
    return KeyboardBuilder.keyboard(*rows)


def pb_keyboard_message(keyboard, map_name: str):
    """Keyboard messages still need a Markdown payload for QQ msg_type=2."""
    return MessageSegment.markdown(MessageMarkdown(content=map_name)) + keyboard


def pr_markdown_content(player_name: str, map_name: str, lines: list[str]) -> str:
    """Render a recent-record card using QQ Markdown and an unordered list."""
    return "\n\n".join((
        f"# {player_name} 的`近期记录`",
        f"![{map_name}]({PR_IMAGE_BASE_URL}/{map_name}.webp)",
        "\n".join(f"- {line}" for line in lines),
    ))


def record_sections_markdown_content(
    title: str, map_name: str, sections: list[tuple[str, list[str]]]
) -> str:
    """Render a titled record card with map image and detail sections."""
    parts = [f"# {title}", f"![{map_name}]({PR_IMAGE_BASE_URL}/{map_name}.webp)"]
    for heading, lines in sections:
        parts.append(f"## {heading}\n" + "\n".join(f"- {line}" for line in lines))
    return "\n\n".join(parts)


def pb_markdown_content(player_name: str, map_name: str, sections: list[tuple[str, list[str]]]) -> str:
    """Render personal-best sections as one Markdown card."""
    return record_sections_markdown_content(
        f"{player_name} 的`个人最佳`", map_name, sections
    )


def wr_markdown_content(map_name: str, sections: list[tuple[str, list[str]]]) -> str:
    """Render world-record sections titled by map rather than record holder."""
    return record_sections_markdown_content(f"{map_name} `世界记录`", map_name, sections)


def normalize_leaderboard_rank(data: dict) -> dict:
    """Adapt the documented v1 rank response to the existing command formatter."""
    player = data.get("player", {})
    return {
        **data,
        "steamid64": player.get("steamid64"),
        "mode": data.get("scope"),
        "region_code": data.get("region"),
        "regional_rank": data.get("rank_regional"),
        "rating": data.get("rating") or 0,
        "maps_easy_rating": data.get("rating_easy") or 0,
        "maps_hard_rating": data.get("rating_hard") or 0,
        "overall_wrs": data.get("wrs_nub") or 0,
        "pro_wrs": data.get("wrs_pro") or 0,
        "map_finished": data.get("unique_map_finishes") or 0,
        "last_updated": "N/A",
    }


def gokz_record_mode_label(record: dict, query_scope: str) -> str:
    """Prefer the concrete mode returned by a GOKZ.TOP record over its scope."""
    try:
        return format_kzmode(record.get("mode"), "m").upper()
    except (TypeError, ValueError):
        return format_kzmode(query_scope, "m").upper()


def gokz_record_rating_line(record: dict) -> str:
    """Render the optional v1 record rating without inventing a default value."""
    rating = record.get("rating")
    return f"║ Rating:　{rating}" if rating is not None else ""


def gokz_record_tier(record: dict):
    """Use the v1 record tier, including for maps absent from the local cache."""
    return record["map_tier"] if record.get("map_tier") is not None else MAP_TIERS.get(
        record["map_name"], "未知"
    )


def convert_to_shanghai_time(date_str):
    """Converts a given datetime string to Asia/Shanghai timezone, handling future dates."""
    if not date_str:
        return "永久封禁"
    original_time = datetime.fromisoformat(date_str)

    # Check for far-future expiration date
    if original_time.year >= 9999:
        return "永久封禁"  # "Permanent Ban" in Chinese

    # Otherwise, convert to Shanghai time
    shanghai_time = original_time.astimezone(ZoneInfo("Asia/Shanghai"))
    return shanghai_time.strftime("%Y-%m-%d %H:%M:%S")


@ban_.handle()
async def _(event: Event, args: Message = CommandArg()):
    cd = CommandData(event, args)
    if cd.error:
        return await ban_.send(cd.error)

    try:
        result = await query(ban_, event, "ban", command_input(cd))
        bans = result.data["bans"]
    except GOKZTopAPIError:
        return await ban_.finish(GOKZ_TOP_UNAVAILABLE, at_sender=True)

    if not bans:
        return await ban_.finish(f"{cd.steamid} 没有找到任何封禁记录。", at_sender=True)

    content = f"玩家: {cd.steamid} 的封禁记录\n"

    for ban in bans:
        ban_type = ban.get("ban_type", "未知")
        player = ban.get("player") or {}
        server = ban.get("server") or {}
        player_name = player.get("display_name", "未知玩家")
        notes = ban.get("notes") or "无"
        server_id = server.get("id") or ban.get("server_id", "未知服务器")

        created_on = convert_to_shanghai_time(ban.get("created_at"))
        expires_on = convert_to_shanghai_time(ban.get("expires_at"))

        content += dedent(f"""
            ╔═════════════
            ║ 玩家: {player_name}
            ║ 封禁类型: {ban_type}
            ║ 服务器ID: {server_id}
            ║ 创建时间: {created_on}
            ║ 解封时间: {expires_on}
            ║ 备注: {notes}
            ╚═════════════
        """).strip() + '\n'

    # Add newline at start for group messages (bot will @ user automatically)
    if getattr(event, 'group_id', None):
        content = '\n' + content
    await ban_.send(content, at_sender=True)


@wr.handle()
async def _(event: Event, args: Message = CommandArg()):
    cd = CommandData(event, args)
    if cd.error:
        return await wr.finish(cd.error)

    if not cd.args:
        return await wr.finish("🗺地图名都不给我怎么帮你查WR (￣^￣) ")


    result = await query(wr, event, "wr", command_input(cd), target=cd.steamid if cd.steamid2 else None)
    map_name = result.data["map_name"]
    kz_mode = cd.mode

    sections = []

    try:
        data = result.data["records"]["NUB"]
        if data:
            sections.append(("Overall世界纪录", [
                f"玩家:　　{data['player_name']}",
                f"模式:　　{gokz_record_mode_label(data, kz_mode)}",
                f"用时:　　{format_gruntime(data['time'])}",
                f"存点数:　{data.get('teleports', 'N/A')}",
                f"分数:　　{data['points']}",
                f"服务器:　{data['server_name']}",
                record_format_time(data.get('created_on') or data.get('updated_on')),
            ]))
        else:
            sections.append(("Overall世界纪录", ["未发现记录"]))
    except GOKZTopAPIError:
        return await wr.finish(GOKZ_TOP_UNAVAILABLE)

    try:
        pro = result.data["records"]["PRO"]
        if pro:
            sections.append(("裸跳世界纪录", [
                f"玩家:　　{pro['player_name']}",
                f"模式:　　{gokz_record_mode_label(pro, kz_mode)}",
                f"用时:　　{format_gruntime(pro['time'])}",
                f"分数:　　{pro['points']}",
                f"服务器:　{pro['server_name']}",
                record_format_time(pro['created_on']),
            ]))
        else:
            sections.append(("裸跳世界纪录", ["未发现记录"]))
    except GOKZTopAPIError:
        return await wr.finish(GOKZ_TOP_UNAVAILABLE)

    concrete_mode = gokz_record_mode_label(data or pro or {}, kz_mode)
    content = wr_markdown_content(map_name, [
        ("地图信息", [f"地图:　　{map_name}", f"难度:　　T{MAP_TIERS.get(map_name, '未知')}", f"模式:　　{concrete_mode}"]),
        *sections,
    ])
    await wr.send(MessageSegment.markdown(MessageMarkdown(content=content)) + pb_action_keyboard(
        event, cd, map_name, include_other_modes=False,
    ))

    # if map_name == 'kz_hb_fafnir':
    #     await wr.send(MessageSegment.file_audio(Path('data/gokz/sound/fafnir.silk')))


@pr.handle()
async def handle_pr(bot: Bot, event: Event, args: Message = CommandArg()):
    cd = CommandData(event, args)
    if cd.error:
        return await pr.finish(cd.error)


    try:
        result = await query(pr, event, "pr", command_input(cd))
        data = result.record
    except GOKZTopAPIError:
        return await pr.finish(GOKZ_TOP_UNAVAILABLE)
    if not data:
        return await pr.finish("未找到最近跳图记录")
    player_name = data.get("player_name", "未知玩家")
    # v1 records carry their own tier.  Prefer it so new maps retain both
    # their display tier and their /pr compliment eligibility.
    map_tier = gokz_record_tier(data)

    lines = [
        f"地图:　　{data['map_name']}",
        f"难度:　　T{map_tier}",
        f"模式:　　{gokz_record_mode_label(data, cd.mode)}",
        f"玩家:　　{player_name}",
        f"用时:　　{format_gruntime(data['time'])}",
        f"存点数:　{data['teleports']}",
        f"分数:　　{data['points']}",
        f"服务器:　{data['server_name']}",
        record_format_time(data['created_on']),
    ]
    content = pr_markdown_content(player_name, data['map_name'], lines)
    await bot.send(event, MessageSegment.markdown(MessageMarkdown(content=content)) + pb_action_keyboard(
        event, cd, data['map_name'], include_other_modes=False,
    ))
    compliment_record = {**data, "map_tier": map_tier}
    force_compliment = is_dev_superuser(event)
    if force_compliment or is_notable_run(compliment_record):
        asyncio.create_task(
            maybe_send_pr_compliment(
                bot,
                event,
                compliment_record,
                cd.steamid,
                force=force_compliment,
            )
        )


@pb.handle()
async def map_pb(bot: Bot, event: Event, args: Message = CommandArg()):
    cd = CommandData(event, args)
    if cd.error:
        return await pb.finish(cd.error)

    if not cd.args:
        return await wr.finish("🗺地图名都不给我怎么帮你查PB (￣^￣) ")


    result = await query(pb, event, "pb", command_input(cd), target=cd.steamid if cd.steamid2 else None)
    map_name = result.data["map_name"]
    data, pro = result.data["records"]["NUB"], result.data["records"]["PRO"]
    sections = []

    if data:
        lines = [
            f"玩家:　　{data['player_name']}",
            f"模式:　　{gokz_record_mode_label(data, cd.mode)}",
            f"用时:　　{format_gruntime(data['time'])}",
            f"存点数:　{data['teleports']}",
            f"分数:　　{data['points']}",
        ]
        if rating_line := gokz_record_rating_line(data):
            lines.append(rating_line.removeprefix("║ "))
        lines.extend((
            f"服务器:　{data['server_name']}",
            record_format_time(data['created_on']),
        ))
        sections.append(("存点记录", lines))
    else:
        sections.append(("存点记录", ["未发现记录"]))

    if pro:
        lines = [
            f"玩家:　　{pro['player_name']}",
            f"模式:　　{gokz_record_mode_label(pro, cd.mode)}",
            f"用时:　　{format_gruntime(pro['time'])}",
            f"分数:　　{pro['points']}",
        ]
        if rating_line := gokz_record_rating_line(pro):
            lines.append(rating_line.removeprefix("║ "))
        lines.extend((
            f"服务器:　{pro['server_name']}",
            record_format_time(pro['created_on']),
        ))
        sections.append(("裸跳记录", lines))
    else:
        sections.append(("裸跳记录", ["未发现记录"]))

    player_name = (data or pro or {}).get("player_name", "未知玩家")
    concrete_mode = gokz_record_mode_label(data or pro or {}, cd.mode)
    content = pb_markdown_content(player_name, map_name, [
        ("地图信息", [
            f"地图:　　{map_name}",
            f"难度:　　T{MAP_TIERS.get(map_name, '未知')}",
            f"模式:　　{concrete_mode}",
        ]),
        *sections,
    ])
    await bot.send(event, MessageSegment.markdown(MessageMarkdown(content=content)) + pb_action_keyboard(
        event, cd, map_name, include_other_modes=False,
    ))


@rank.handle()
async def handle_rank(bot: Bot, event: Event, args: Message = CommandArg()):
    cd = CommandData(event, args)
    if cd.error:
        return await rank.finish(cd.error)


    result = await query(rank, event, "rank", command_input(cd))
    player_data = result.data["player"]
    player_name = player_data.get("alias") or player_data.get("name", "N/A")
    rank_data = normalize_leaderboard_rank(result.data["rank"])
    if cd.update:
        # Format response with update information
        differ = rank_data.get('differ', {})
        
        content = dedent(f"""
            ╔════════════
            ║ 玩家:　　　{player_name}
            ║ SteamID64: {rank_data.get('steamid64', 'N/A')}
            ║ 模式:　　　{rank_data.get('mode', 'N/A')}
        """).strip()
        
        # Add rank if available (just below mode)
        if rank_data.get('rank'):
            rank_value = rank_data.get('rank')
            rank_change = differ.get('rank', 0)
            if rank_change != 0:
                sign = '+' if rank_change > 0 else ''
                content += f"\n║ 全球排名:　No.{rank_value}({sign}{rank_change})"
            else:
                content += f"\n║ 全球排名:　No.{rank_value}"
        
        # Add regional rank if available (just below mode)
        if rank_data.get('region_code') and rank_data.get('regional_rank') is not None:
            region_code = rank_data.get('region_code', '')
            regional_rank = rank_data.get('regional_rank')
            rank_change = differ.get('regional_rank', 0)
            if rank_change != 0:
                sign = '+' if rank_change > 0 else ''
                content += f"\n║ 地区排名：{region_code}#{regional_rank}({sign}{rank_change})"
            else:
                content += f"\n║ 地区排名：{region_code}#{regional_rank}"
        
        # Format values with inline changes
        points = rank_data.get('points', 0)
        points_change = differ.get('points', 0)
        points_str = f"{points:,}"
        if points_change != 0:
            sign = '+' if points_change > 0 else ''
            points_str += f"({sign}{points_change:,})"
        
        total_points_v2 = rank_data.get('total_points_v2', 0)
        total_points_v2_change = differ.get('total_points_v2', 0)
        total_points_v2_str = f"{total_points_v2:,}"
        if total_points_v2_change != 0:
            sign = '+' if total_points_v2_change > 0 else ''
            total_points_v2_str += f"({sign}{total_points_v2_change:,})"
        
        # Format ratings with 4 decimal places (floored) for changes
        rating = rank_data.get('rating', 0)
        rating_change = differ.get('rating', 0)
        rating_str = f"{rating:.2f}"
        if rating_change != 0:
            sign = '+' if rating_change > 0 else ''
            # Floor the change value to 4 decimal places
            floored_change = math.floor(abs(rating_change) * 10000) / 10000
            rating_str += f"({sign}{floored_change:.4f})"
        
        maps_easy_rating = rank_data.get('maps_easy_rating', 0)
        maps_easy_rating_change = differ.get('maps_easy_rating', 0)
        maps_easy_rating_str = f"{maps_easy_rating:.2f}"
        if maps_easy_rating_change != 0:
            sign = '+' if maps_easy_rating_change > 0 else ''
            floored_change = math.floor(abs(maps_easy_rating_change) * 10000) / 10000
            maps_easy_rating_str += f"({sign}{floored_change:.4f})"
        
        maps_hard_rating = rank_data.get('maps_hard_rating', 0)
        maps_hard_rating_change = differ.get('maps_hard_rating', 0)
        maps_hard_rating_str = f"{maps_hard_rating:.2f}"
        if maps_hard_rating_change != 0:
            sign = '+' if maps_hard_rating_change > 0 else ''
            floored_change = math.floor(abs(maps_hard_rating_change) * 10000) / 10000
            maps_hard_rating_str += f"({sign}{floored_change:.4f})"
        
        overall_wrs = rank_data.get('overall_wrs', 0)
        overall_wrs_change = differ.get('overall_wrs', 0)
        overall_wrs_str = str(overall_wrs)
        if overall_wrs_change != 0:
            sign = '+' if overall_wrs_change > 0 else ''
            overall_wrs_str += f"({sign}{overall_wrs_change})"
        
        pro_wrs = rank_data.get('pro_wrs', 0)
        pro_wrs_change = differ.get('pro_wrs', 0)
        pro_wrs_str = str(pro_wrs)
        if pro_wrs_change != 0:
            sign = '+' if pro_wrs_change > 0 else ''
            pro_wrs_str += f"({sign}{pro_wrs_change})"
        
        map_finished = rank_data.get('map_finished', 0)
        map_finished_change = differ.get('map_finished', 0)
        map_finished_str = str(map_finished)
        if map_finished_change != 0:
            sign = '+' if map_finished_change > 0 else ''
            map_finished_str += f"({sign}{map_finished_change})"
        
        content += "\n" + dedent(f"""
            ║ 总分V1:　　{points_str}
            ║ 总分v2:　　{total_points_v2_str}
            ║ Rating:　　{rating_str}
            ║ Rating.E:　{maps_easy_rating_str}
            ║ Rating.H:　{maps_hard_rating_str}
        """).strip()
        
        t5 = rank_data.get('t5_finishes', 0)
        t6 = rank_data.get('t6_finishes', 0)
        t7 = rank_data.get('t7_finishes', 0)
        t8 = rank_data.get('t8_finishes', 0)
        
        content += "\n" + dedent(f"""
            ║ OVR WRs: {overall_wrs_str}  PRO WRS: {pro_wrs_str}
            ║ T5: {t5} | T6: {t6} | T7: {t7} | T8: {t8}
            ║ 完成地图数: {map_finished_str}
            ║ 最后更新:　{rank_data.get('last_updated', 'N/A').replace('T', ' ')[:19]}
            ╚═════════════
        """).strip()
    else:
        content = dedent(f"""
            ╔════════════
            ║ 玩家:　　　{player_name}
            ║ 模式:　　　{rank_data.get('mode', 'N/A')}
        """).strip()
        
        # Add rank if available (just below mode)
        if rank_data.get('rank'):
            content += f"\n║ 全球排名:　No.{rank_data.get('rank')}"
        
        # Add regional rank if available (just below mode)
        if rank_data.get('region_code') and rank_data.get('regional_rank') is not None:
            region_code = rank_data.get('region_code', '')
            regional_rank = rank_data.get('regional_rank')
            content += f"\n║ 地区排名：{region_code}#{regional_rank}"
        
        content += "\n" + dedent(f"""
            ║ 总分V1:　　{rank_data.get('points', 0):,}
            ║ 总分v2:　　{rank_data.get('total_points_v2', 0):,}
            ║ Rating:　　{rank_data.get('rating', 0):.2f}
            ║ Rating.E:　{rank_data.get('maps_easy_rating', 0):.2f}
            ║ Rating.H:　{rank_data.get('maps_hard_rating', 0):.2f}
        """).strip()
        
        t5 = rank_data.get('t5_finishes', 0)
        t6 = rank_data.get('t6_finishes', 0)
        t7 = rank_data.get('t7_finishes', 0)
        t8 = rank_data.get('t8_finishes', 0)
        
        content += "\n" + dedent(f"""
            ║ OVR WRs: {rank_data.get('overall_wrs', 0)}  PRO WRS: {rank_data.get('pro_wrs', 0)}
            ║ T5: {t5} | T6: {t6} | T7: {t7} | T8: {t8}
            ║ 完成地图数: {rank_data.get('map_finished', 0)}
            ║ SteamID64: {rank_data.get('steamid64', 'N/A')}
            ║ 最后更新:　{rank_data.get('last_updated', 'N/A').replace('T', ' ')[:19]}
            ╚═════════════
        """).strip()
    
    # Add newline at start for group messages (bot will @ user automatically)
    if getattr(event, 'group_id', None):
        content = '\n' + content
    
    await rank.finish(content)


@review.handle()
async def handle_review(bot: Bot, event: Event, args: Message = CommandArg()):
    """Handle /review map_name command to show map reviews"""
    if not args:
        return await review.finish("🗺地图名都不给我怎么帮你查评价 (￣^￣) ")
    
    result = await query(review, event, "review", CommandInput(arguments=(args.extract_plain_text().strip(),)))
    map_data = result.data["map"]
    map_name = map_data["name"]
    ratings = result.data["ratings"]
    if not ratings:
        return await review.finish(f"地图 {map_name} 暂无评价数据。")
    overall_avg, overall_count = result.data["summary"]["overall"]
    visuals_avg, visuals_count = result.data["summary"]["visuals"]
    gameplay_avg, gameplay_count = result.data["summary"]["gameplay"]
    comment_count = result.data["comment_count"]
    author_names = [author if isinstance(author, str) else author.get('name', '未知作者') for author in map_data.get('authors', [])]
    # Build summary content
    content = dedent(f"""
        ╔ 地图:　{map_name}
        ║ 难度:　T{MAP_TIERS.get(map_name, '未知')}
    """).strip()
    
    # Append author information if available
    if author_names:
        authors_str = ', '.join(author_names)
        content += f"\n║ 作者:　{authors_str}"
    
    content += "\n" + dedent(f"""
        ╠═════评价统计═════
        ║ 总体评分:　{overall_avg:.1f}⭐ ({overall_count}人评价)
        ║ 视觉评分:　{visuals_avg:.1f}⭐ ({visuals_count}人评价)
        ║ 玩法评分:　{gameplay_avg:.1f}⭐ ({gameplay_count}人评价)
        ║ 评论数量:　{comment_count}
    """).strip()
    
    comments_data = result.data["comments"]

    if comments_data and isinstance(comments_data, dict):
        comments_count = comments_data.get('count', 0)
        comments_list = comments_data.get('data', [])
        
        if comments_count == 0 or not comments_list or len(comments_list) == 0:
            content += "\n╠═════玩家评论═════"
            content += "\n║ 暂无评论"
        else:
            content += "\n╠═════玩家评论═════"
            
            # Show up to 5 most recent comments
            for idx, comment_item in enumerate(comments_list[:5], 1):
                player_name = comment_item.get('player', {}).get('display_name', '未知玩家')
                review_content = comment_item.get('content', {})
                comment_value = review_content.get('comment')
                comment_text = (
                    comment_value.get('text', '') if isinstance(comment_value, dict) else comment_value or ''
                )
                
                # Get overall rating from ratings array
                overall_rating = review_content.get('overall')
                
                rating_str = f"{overall_rating}⭐" if overall_rating else "未评分"
                
                if comment_text:
                    content += f"\n║ {idx}. {player_name} ({rating_str})"
                    # Truncate long comments
                    if len(comment_text) > 50:
                        comment_text = comment_text[:47] + "..."
                    content += f"\n║    {comment_text}"
                else:
                    content += f"\n║ {idx}. {player_name} ({rating_str})"
            
            if len(comments_list) > 5:
                content += f"\n║ ... 还有 {len(comments_list) - 5} 条评论"
    
    content += "\n╚═════════════"
    
    # Add newline at start for group messages
    if getattr(event, 'group_id', None):
        content = '\n' + content
    
    await review.finish(content)


@rate.handle()
async def handle_rate(bot: Bot, event: Event, args: Message = CommandArg()):
    """Handle /rate command to rate a map
    
    Usage:
        /rate map_name overall_star [comments]
        /rate map_name overall_star gameplay_star visual_star [comments]
        /rate map_name comments
    """
    cd = CommandData(event, args)
    if cd.error:
        return await rate.finish(cd.error)
    
    if not args:
        return await rate.finish("🗺地图名都不给我怎么帮你评分 (￣^￣) ")
    
    # Keep QQ's whitespace grammar; named Discord options reach the same feature.
    request = command_input(cd)
    request.arguments = tuple(args.extract_plain_text().strip().split())
    result = await query(rate, event, "rate", request)
    map_name = result.data["map_name"]
    if not result.data.get("saved"):
        return await rate.finish(rate_selection_message(map_name, result.data.get("current_rating")))
    overall_star = result.data["content"]["overall"]
    content = f"✅ 已成功为地图 {map_name} 评分:\n总体评分: {overall_star}⭐"
    
    # Add newline at start for group messages
    if getattr(event, 'group_id', None):
        content = '\n' + content
    
    await rate.finish(content)


@comment.handle()
async def handle_comment(event: Event, args: Message = CommandArg()):
    """Attach or update a comment without changing the user's star rating."""
    cd = CommandData(event, args)
    if cd.error:
        return await comment.finish(cd.error)

    args_list = args.extract_plain_text().strip().split(maxsplit=1)
    if len(args_list) < 2 or not args_list[1].strip():
        return await comment.finish("用法: /comment map_name 评论内容")

    request = command_input(cd)
    request.arguments = (args_list[0],)
    request.comment = args_list[1].strip()
    result = await query(comment, event, "comment", request)
    map_name = result.data["map_name"]
    await comment.finish(f"✅ 已为地图 {map_name} 提交评论。")


@kz.handle()
async def handle_kz(bot: Bot, event: Event, args: Message = CommandArg()):
    cd = CommandData(event, args)
    if cd.error:
        return await bot.send(event, cd.error)

    await bot.send(event, "正在生成玩家卡片…")
    try:
        result = await query(kz, event, "kz", command_input(cd))
        url = result.file
    except FinishedException:
        raise
    except Exception as exc:
        logger.warning(f"Player card failed for {cd.steamid}: {type(exc).__name__}")
        return await bot.send(event, f"玩家卡片生成失败，可直接查看资料：\nhttps://gokz.top/profile/{cd.steamid}")

    image_path = Path(url)
    if image_path.exists():
        await bot.send(event, MessageSegment.file_image(image_path))
    else:
        await bot.send(event, "图片生成失败，请稍后重试。")
