import asyncio
import math
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from textwrap import dedent
from zoneinfo import ZoneInfo

from nonebot import on_command, logger
from nonebot.adapters.qq import Bot, Event, Message, MessageSegment
from nonebot.adapters.qq.models import MessageMarkdown
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER

from ..api.kztimerglobal import fetch_personal_best, fetch_personal_recent, fetch_world_record, fetch_overall_world_record, fetch_personal_bans, \
    update_map_data
from ..api import cs2kz
from ..api.helper import fetch_json, put_json, post_json
from src.plugins.gokz.core.command_helper import CommandData
from src.plugins.gokz.core.config import MAP_TIERS
from src.plugins.gokz.core.formatter import format_gruntime, record_format_time
from src.plugins.gokz.core.game import format_cs2kz_mode_label
from src.plugins.gokz.core.kreedz import format_kzmode
from src.plugins.gokz.core.kz.screenshot import cs2kz_screenshot_async, vnl_screenshot_async, kzgoeu_screenshot_async
from src.plugins.gokz.core.map_img_url import (
    get_cs2kz_preferred_map_img_path,
    get_map_img_url,
)
from src.plugins.gokz.core.map_selection import (
    map_command,
    map_selection_message,
    resolve_map_name,
)
from src.plugins.gokz.core.keyboard import KeyboardBuilder
from src.plugins.gokz.core.rate_message import rate_selection_message
from ..config import GOKZ_TOP_API_KEY

pb = on_command('pb', aliases={'personal-best'})
pr = on_command('pr')
kz = on_command('kz', aliases={'kzgo'})
wr = on_command('wr')
ban_ = on_command('ban')
rank = on_command('rank')
review = on_command('review', aliases={'评价', '评论'})
rate = on_command('rate', aliases={'评分', '评价地图'})
comment = on_command('comment', aliases={'地图评论'})
update_map_info = on_command('update_map', permission=SUPERUSER)

private_map_names: dict[int, str] = {}  # For private messages
group_map_names: dict[int, str] = {}  # For group messages

DEFAULT_MAP = 'bkz_cakewalk'
GOKZ_TOP_V1 = "https://api.gokz.top/v1"


def selected_gokz_command(command: str, map_name: str, cd: CommandData) -> str:
    """Recreate a GOKZ query after a user chooses an ambiguous map."""
    arguments = ("-m", str(cd.mode))
    if cd.steamid2:
        arguments += ("-s", cd.steamid)
    return map_command(command, map_name, *arguments)


def pb_action_keyboard(event: Event, cd: CommandData, map_name: str, course: str | None = None):
    """Build follow-up actions for a PB result.

    The self-query action is useful only when a group member queried another
    player (``CommandData.steamid2`` is set for that case).  ``enter=True``
    makes QQ submit the command directly after the user taps the button.
    """
    mode = f" -m {cd.mode}" if cd.mode else ""
    game = " -2" if cd.game == "cs2kz" else ""
    course_arg = f" -c {course}" if course and cd.game == "cs2kz" and course != "Main" else ""
    target_arg = f" -s {cd.steamid}" if cd.steamid2 and cd.steamid != cd.steamid2 else ""
    if cd.game == "cs2kz":
        other_modes = [("VNL", "vanilla")] if cd.mode == "classic" else [("CKZ", "classic")]
    else:
        current_mode = format_kzmode(cd.mode, "m")
        other_modes = [
            (label, value)
            for label, value in (("KZT", "kzt"), ("SKZ", "skz"), ("VNL", "vnl"))
            if value != current_mode
        ]
    actions = []
    if getattr(event, "group_id", None) and cd.steamid2 and cd.steamid != cd.steamid2:
        actions.append(
            KeyboardBuilder.button(
                id="pb_self",
                label="查询我的",
                visited_label="查询中",
                style=1,
                action_type=2,
                permission_type=2,
                action_data=f"/pb {map_name}{mode}{game}{course_arg}",
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
            action_data=f"/wr {map_name}{mode}{game}{course_arg}",
            reply=True,
            enter=True,
        )
    )
    if cd.game != "cs2kz":
        actions.append(
            KeyboardBuilder.button(
                id="pb_leaderboard",
                label="查看排行榜",
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
            label="查询地图进度",
            visited_label="查询中",
            style=1,
            action_type=2,
            permission_type=2,
            action_data=f"/mp {map_name}{mode}{game}{course_arg}{target_arg}",
            reply=True,
            enter=True,
        )
    )
    actions.extend(
        KeyboardBuilder.button(
            id=f"pb_{other_mode}",
            label=f"查询{label}",
            visited_label="查询中",
            style=1,
            action_type=2,
            permission_type=2,
            action_data=f"/pb {map_name} -m {other_mode}{game}{course_arg}{target_arg}",
            reply=True,
            enter=True,
        )
        for label, other_mode in other_modes
    )
    actions.append(
        KeyboardBuilder.button(
            id="pb_rate",
            label="为地图评分",
            visited_label="打开评分",
            style=1,
            action_type=2,
            permission_type=2,
            action_data=f"/rate {map_name}",
            reply=True,
            enter=True,
        )
    )
    return KeyboardBuilder.keyboard(*(actions[index:index + 2] for index in range(0, len(actions), 2)))


def pb_keyboard_message(keyboard, map_name: str):
    """Keyboard messages still need a Markdown payload for QQ msg_type=2."""
    return MessageSegment.markdown(MessageMarkdown(content=map_name)) + keyboard


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


def cs2_record_text(record: dict, pro: bool | None = None) -> str:
    return dedent(f"""
        ║ 玩家:　　{record['player']['name']}
        ║ 用时:　　{format_gruntime(record['time'])}
        ║ 存点:　　{record['teleports']}
        ║ 分数:　　{(cs2kz.record_points(record, pro) or 0):.0f}
        ║ 排名:　　#{cs2kz.record_rank(record, pro) or '-'}
        ║ 服务器:　{record['server']['name']}""").strip()


@update_map_info.handle()
async def _():
    await update_map_data()
    await update_map_info.finish('更新完成')


def convert_to_shanghai_time(date_str):
    """Converts a given datetime string to Asia/Shanghai timezone, handling future dates."""
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

    bans = await fetch_personal_bans(steamid64=cd.steamid)

    if not bans:
        return await ban_.finish(f"{cd.steamid} 没有找到任何封禁记录。", at_sender=True)

    content = f"玩家: {cd.steamid} 的封禁记录\n"

    for ban in bans:
        ban_type = ban.get("ban_type", "未知")
        player_name = ban.get("player_name", "未知玩家")
        notes = ban.get("notes", "无")
        server_id = ban.get("server_id", "未知服务器")

        created_on = convert_to_shanghai_time(ban["created_on"])
        expires_on = convert_to_shanghai_time(ban["expires_on"])

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

    if cd.game == "cs2kz":
        map_data = await cs2kz.fetch_map(cd.args[0])
        if not map_data:
            return await wr.finish("未找到CS2KZ地图")
        map_name = map_data["name"]
        course = cs2kz.find_course(map_data, cd.course)
        tp_records = await cs2kz.fetch_records(map_name=map_name, course=course, mode=cd.mode, max_rank=1, limit=1)
        pro_records = await cs2kz.fetch_records(map_name=map_name, course=course, mode=cd.mode, has_teleports=False, max_rank=1, limit=1)
        content = f"╔ 地图:　{map_name}\n║ 关卡:　{course}\n║ 模式:　{format_cs2kz_mode_label(cd.mode)}\n╠═════NUB记录═════"
        content += cs2_record_text(tp_records[0], False) if tp_records else "\n║ 未发现NUB记录"
        content += "\n╠═════PRO记录═════"
        content += cs2_record_text(pro_records[0], True) if pro_records else "\n║ 未发现PRO记录"
        content += "\n╚ CS2KZ ═══"
        img_path = await get_cs2kz_preferred_map_img_path(map_name)
        if not img_path:
            return
        return await wr.send(MessageSegment.file_image(img_path) + MessageSegment.text(content))

    map_name, candidates = resolve_map_name(cd.args[0])
    if candidates:
        return await wr.finish(map_selection_message(
            candidates,
            lambda selected: selected_gokz_command("wr", selected, cd),
            event.get_user_id(),
        ))
    if not map_name:
        return await wr.finish("未找到该地图")

    kz_mode = cd.mode

    content = dedent(f"""
        ╔ 地图:　{map_name}
        ║ 难度:　T{MAP_TIERS.get(map_name, '未知')}
        ║ 模式:　{kz_mode}
        ╠═════Overall记录═════
    """).strip()

    try:
        data = await fetch_overall_world_record(map_name, mode=kz_mode)
        content += dedent(f"""
            ║ {data['steam_id']}
            ║ 昵称:　　{data['player_name']}
            ║ 用时:　　{format_gruntime(data['time'])}
            ║ 存点数:　{data.get('teleports', 'N/A')}
            ║ 分数:　　{data['points']}
            ║ 服务器:　{data['server_name']}
            ║ {record_format_time(data.get('created_on') or data.get('updated_on'))}""")
    except IndexError:
        content += f"\n╠ 未发现Overall记录:"

    content += f"\n╠═════裸跳记录═════"
    try:
        pro = await fetch_world_record(map_name, mode=kz_mode, has_tp=False)
        content += dedent(f"""
            ║ {pro['steam_id']}
            ║ 昵称:　　{pro['player_name']}
            ║ 用时:　　{format_gruntime(pro['time'])}
            ║ 分数:　　{pro['points']}
            ║ 服务器:　{pro['server_name']}
            ╚ {record_format_time(pro['created_on'])}═══
        """)
    except IndexError:
        content += f"\n未发现裸跳记录:"

    img_path = await get_map_img_url(map_name)
    # Add newline at start for group messages (bot will @ user automatically)
    if getattr(event, 'group_id', None):
        content = '\n' + content
    if img_path and img_path.exists():
        combined_message = MessageSegment.file_image(img_path) + MessageSegment.text(content)
    else:
        combined_message = MessageSegment.text(content)
    await wr.send(combined_message)

    # if map_name == 'kz_hb_fafnir':
    #     await wr.send(MessageSegment.file_audio(Path('data/gokz/sound/fafnir.silk')))


@pr.handle()
async def handle_pr(bot: Bot, event: Event, args: Message = CommandArg()):
    cd = CommandData(event, args)
    if cd.error:
        return await pr.finish(cd.error)

    if cd.game == "cs2kz":
        records = await cs2kz.fetch_records(player=cd.steamid, mode=cd.mode, limit=1)
        if not records:
            return await pr.finish("未找到CS2KZ最近记录")
        data = records[0]
        content = "\n".join((
            f"╔ 地图:　　{data['map']['name']}",
            f"║ 关卡:　　{data['course']['name']}",
            f"║ 模式:　　{format_cs2kz_mode_label(cd.mode)}",
            cs2_record_text(data),
            "╚ CS2KZ ═══",
        ))
        img_path = await get_cs2kz_preferred_map_img_path(data['map']['name'])
        if img_path:
            await bot.send(event, MessageSegment.file_image(img_path) + MessageSegment.text(content))
        else:
            await bot.send(event, MessageSegment.text(content))
        return await bot.send(event, pb_keyboard_message(
            pb_action_keyboard(event, cd, data['map']['name'], data['course']['name']),
            data['map']['name'],
        ))

    data = await fetch_personal_recent(cd.steamid, cd.mode)

    content = dedent(f"""
        ╔ 地图:　　{data['map_name']}
        ║ 难度:　　T{MAP_TIERS.get(data['map_name'], '未知')}
        ║ 模式:　　{cd.mode}
        ║ 玩家:　　{data['player_name']} 
        ║ 用时:　　{format_gruntime(data['time'])}
        ║ 存点数:　{data['teleports']}
        ║ 分数:　　{data['points']}
        ║ 服务器:　{data['server_name']}
        ╚ {record_format_time(data['created_on'])} ═══""").strip()

    img_path = await get_map_img_url(data['map_name'])
    # Add newline at start for group messages (bot will @ user automatically)
    if getattr(event, 'group_id', None):
        content = '\n' + content
    if img_path and img_path.exists():
        combined_message = MessageSegment.file_image(img_path) + MessageSegment.text(content)
    else:
        combined_message = MessageSegment.text(content)

    await bot.send(event, combined_message)
    await bot.send(event, pb_keyboard_message(pb_action_keyboard(event, cd, data['map_name']), data['map_name']))


@pb.handle()
async def map_pb(bot: Bot, event: Event, args: Message = CommandArg()):
    cd = CommandData(event, args)
    if cd.error:
        return await pb.finish(cd.error)

    if not cd.args:
        return await wr.finish("🗺地图名都不给我怎么帮你查PB (￣^￣) ")

    if cd.game == "cs2kz":
        map_data = await cs2kz.fetch_map(cd.args[0])
        if not map_data:
            return await pb.finish("未找到CS2KZ地图")
        map_name = map_data["name"]
        course = cs2kz.find_course(map_data, cd.course)
        tp_records = await cs2kz.fetch_records(player=cd.steamid, map_name=map_name, course=course, mode=cd.mode, top=True, limit=1)
        pro_records = await cs2kz.fetch_records(player=cd.steamid, map_name=map_name, course=course, mode=cd.mode, top=True, has_teleports=False, limit=1)
        content = f"╔ 地图:　{map_name}\n║ 关卡:　{course}\n║ 模式:　{format_cs2kz_mode_label(cd.mode)}\n╠═════NUB记录═════"
        content += cs2_record_text(tp_records[0], False) if tp_records else "\n║ 未发现NUB记录"
        content += "\n╠═════PRO记录═════"
        content += cs2_record_text(pro_records[0], True) if pro_records else "\n║ 未发现PRO记录"
        content += "\n╚ CS2KZ ═══"
        img_path = await get_cs2kz_preferred_map_img_path(map_name)
        if img_path:
            await bot.send(event, MessageSegment.file_image(img_path) + MessageSegment.text(content))
        else:
            await bot.send(event, MessageSegment.text(content))
        return await bot.send(event, pb_keyboard_message(
            pb_action_keyboard(event, cd, map_name, course), map_name,
        ))

    map_name, candidates = resolve_map_name(cd.args[0])
    if candidates:
        return await pb.finish(map_selection_message(
            candidates,
            lambda selected: selected_gokz_command("pb", selected, cd),
            event.get_user_id(),
        ))
    if not map_name:
        return await pb.finish("未找到该地图")

    content = dedent(f"""
        ╔ 地图:　{map_name}
        ║ 难度:　T{MAP_TIERS.get(map_name, '未知')}
        ║ 模式:　{cd.mode}
        ╠═════存点记录═════""").strip()

    try:
        data = await fetch_personal_best(cd.steamid, map_name, cd.mode)
        if data:
            content += dedent(f"""
                ║ 玩家:　　{data['player_name']}
                ║ 用时:　　{format_gruntime(data['time'])}
                ║ 存点:　　{data['teleports']}
                ║ 分数:　　{data['points']}
                ║ 服务器:　{data['server_name']}
                ║ {record_format_time(data['created_on'])} """)
        else:
            content += f"\n║ 未发现存点记录"
    except Exception as e:
        logger.info(repr(e))
        content += f"\n║ 未发现存点记录"

    content += f"\n╠═════裸跳记录═════"

    try:
        pro = await fetch_personal_best(cd.steamid, map_name, cd.mode, has_tp=False)
        if pro:
            content += dedent(f"""
                ║ 玩家:　　{pro['player_name']}
                ║ 用时:　　{format_gruntime(pro['time'])}
                ║ 分数:　　{pro['points']}
                ║ 服务器:　{pro['server_name']}
                ╚ {record_format_time(pro['created_on'])} ═══""")
        else:
            content += f"\n╚ 未发现裸跳记录"
    except Exception as e:
        logger.info(repr(e))
        content += f"\n╚ 未发现裸跳记录"

    # Add newline at start for group messages (bot will @ user automatically)
    if getattr(event, 'group_id', None):
        content = '\n' + content
    img_path = await get_map_img_url(map_name)
    if img_path and img_path.exists():
        await bot.send(event, MessageSegment.file_image(img_path) + MessageSegment.text(content))
    else:
        await bot.send(event, MessageSegment.text(content))
    await bot.send(event, pb_keyboard_message(pb_action_keyboard(event, cd, map_name), map_name))


@rank.handle()
async def handle_rank(bot: Bot, event: Event, args: Message = CommandArg()):
    cd = CommandData(event, args)
    if cd.error:
        return await rank.finish(cd.error)

    if cd.game == "cs2kz":
        player = await cs2kz.fetch_player(cd.steamid)
        if not player:
            return await rank.finish("未找到CS2KZ玩家")
        rank_ckz, rank_vnl = await asyncio.gather(
            cs2kz.fetch_global_rank(player["id"], player.get("ckz_rating", 0), "classic"),
            cs2kz.fetch_global_rank(player["id"], player.get("vnl_rating", 0), "vanilla"),
        )
        content = dedent(f"""
            ╔════════════
            ║ 玩家:　　　{player['name']}
            ║ SteamID:　 {player['id']}
            ║ 游戏:　　　CS2KZ
            ║ Rating CKZ: {player.get('ckz_rating', 0):.0f}
            ║ Rank CKZ:　{f'#{rank_ckz}' if rank_ckz is not None else '-'}
            ║ Rating VNL: {player.get('vnl_rating', 0):.0f}
            ║ Rank VNL:　{f'#{rank_vnl}' if rank_vnl is not None else '-'}
            ║ Prime:　　 {'已验证' if player.get('is_prime_verified') else '未验证'}
            ╚════════════""").strip()
        return await rank.finish(content)

    leaderboard_url = f"{GOKZ_TOP_V1}/leaderboards/players/{cd.steamid}"
    player_url = f"{GOKZ_TOP_V1}/players/{cd.steamid}"
    
    # Player and leaderboard reads are public v1 endpoints.
    headers = {}
    
    # Fetch player info to get name/alias (silently ignore errors)
    player_name = 'N/A'
    try:
        player_data = await fetch_json(player_url, timeout=30, headers=headers)
        # Only use player_data if it's a valid success response (not an error response)
        if player_data and isinstance(player_data, dict) and 'detail' not in player_data:
            player_name = player_data.get('alias') or player_data.get('name', 'N/A')
    except Exception:
        # Silently ignore any errors when fetching player info
        pass
    
    # If update flag is set, use PUT request with kz_timer format
    if cd.update:
        update_data = await put_json(leaderboard_url, timeout=30, headers=headers)
        if update_data is None:
            return await rank.finish("gokz-top API服务暂时不可用，请稍后再试。")
        
        # Check for error response (API returned non-200 with detail field)
        if isinstance(update_data, dict) and update_data.get('detail'):
            return await rank.finish(update_data.get('detail'))

        params = {"scope": format_kzmode(cd.mode, 'm').upper()}
        rank_data = await fetch_json(leaderboard_url, params=params, timeout=30, headers=headers)
        
        # Check if response is not a valid success response (missing required fields)
        if not isinstance(rank_data, dict) or rank_data.get('detail'):
            return await rank.finish("gokz-top API返回了无效数据，请稍后再试。")
        rank_data = normalize_leaderboard_rank(rank_data)
        
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
        params = {"scope": format_kzmode(cd.mode, 'm').upper()}
        rank_data = await fetch_json(leaderboard_url, params=params, timeout=30, headers=headers)
        if rank_data is None:
            return await rank.finish("gokz-top API服务暂时不可用，请稍后再试。")
        
        # Check for error response (API returned non-200 with detail field)
        if isinstance(rank_data, dict) and rank_data.get('detail'):
            return await rank.finish(rank_data.get('detail'))
        
        # Check if response is not a valid success response (missing required fields)
        if not isinstance(rank_data, dict) or rank_data.get('detail'):
            return await rank.finish("gokz-top API返回了无效数据，请稍后再试。")
        rank_data = normalize_leaderboard_rank(rank_data)
        
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
    
    map_name, candidates = resolve_map_name(args.extract_plain_text().strip())
    if candidates:
        return await review.finish(map_selection_message(
            candidates,
            lambda selected: map_command("review", selected),
            event.get_user_id(),
        ))
    if not map_name:
        return await review.finish("未找到该地图，请检查地图名是否正确。")
    
    BASE_URL = GOKZ_TOP_V1
    
    # Review reads are public v1 endpoints.
    headers = {}
    
    # Fetch review summary
    summary_url = f"{BASE_URL}/maps/reviews"
    summary_params = {"map_name": map_name, "limit": 100}
    summary_data = await fetch_json(summary_url, params=summary_params, headers=headers, timeout=30)
    
    if summary_data is None:
        return await review.finish("gokz-top API服务暂时不可用，请稍后再试。")
    
    # Check for error response (API returned non-200 with detail field)
    if isinstance(summary_data, dict) and summary_data.get('detail'):
        return await review.finish(summary_data.get('detail'))
    
    # Ensure we have a valid dict response
    if not isinstance(summary_data, dict):
        return await review.finish("gokz-top API返回了无效数据，请稍后再试。")
    
    summary_list = summary_data.get('data', [])
    if not summary_list or len(summary_list) == 0:
        return await review.finish(f"地图 {map_name} 暂无评价数据。")
    
    ratings = [item.get('content', {}) for item in summary_list]
    def average(aspect):
        values = [rating[aspect] for rating in ratings if rating.get(aspect) is not None]
        return (sum(values) / len(values), len(values)) if values else (0, 0)
    overall_avg, overall_count = average('overall')
    visuals_avg, visuals_count = average('visuals')
    gameplay_avg, gameplay_count = average('gameplay')
    comment_count = sum(bool(rating.get('comment')) for rating in ratings)
    
    # Fetch map data to get authors
    map_url = f"{BASE_URL}/maps"
    map_data = await fetch_json(map_url, params={"name": map_name, "limit": 1}, headers=headers, timeout=30)
    
    # Format author names (use alias if available, otherwise name)
    author_names = []
    if isinstance(map_data, list) and map_data:
        authors = map_data[0].get('authors', [])
        for author in authors:
            author_name = author if isinstance(author, str) else author.get('name', '未知作者')
            author_names.append(author_name)
    
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
    
    # Fetch comments from comments endpoint
    comments_url = f"{BASE_URL}/maps/reviews"
    comments_params = {"map_name": map_name, "offset": 0, "limit": 100, "with_comments_only": "true"}
    comments_data = await fetch_json(comments_url, params=comments_params, headers=headers, timeout=30)
    
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
    
    # Parse arguments
    args_text = args.extract_plain_text().strip()
    args_list = args_text.split()
    
    # Search for map name
    map_name, candidates = resolve_map_name(args_list[0])
    if candidates:
        trailing_args = " ".join(args_list[1:])
        return await rate.finish(map_selection_message(
            candidates,
            lambda selected: map_command("rate", selected, trailing_args),
            event.get_user_id(),
        ))
    if not map_name:
        return await rate.finish("未找到该地图，请检查地图名是否正确。")
    
    maps = await fetch_json(f"{GOKZ_TOP_V1}/maps", params={"name": map_name, "limit": 1}, timeout=30)
    if not isinstance(maps, list) or not maps:
        return await rate.finish("未找到该地图，请检查地图名是否正确。")

    if len(args_list) < 2:
        reviews = await fetch_json(
            f"{GOKZ_TOP_V1}/maps/reviews",
            params={"map_id": maps[0]["id"], "steamid64": cd.steamid, "limit": 1},
            timeout=30,
        )
        current_rating = None
        if isinstance(reviews, dict):
            review_data = reviews.get("data")
            if isinstance(review_data, list) and review_data:
                content = review_data[0].get("content")
                if isinstance(content, dict) and isinstance(content.get("overall"), int):
                    current_rating = content["overall"]
        return await rate.finish(rate_selection_message(map_name, current_rating))

    try:
        overall_star = int(args_list[1])
        gameplay_star = int(args_list[2]) if len(args_list) > 3 and args_list[2].isdigit() else None
        visual_star = int(args_list[3]) if gameplay_star is not None and len(args_list) > 3 else None
    except ValueError:
        return await rate.finish("新接口要求提供总体评分 (1-5)。")
    if not all(1 <= value <= 5 for value in (overall_star, gameplay_star, visual_star) if value is not None):
        return await rate.finish("评分必须在1-5之间")

    comment_start = 4 if visual_star is not None else 2
    content = {"overall": overall_star, "gameplay": gameplay_star, "visuals": visual_star}
    if comment_text := ' '.join(args_list[comment_start:]):
        content["comment"] = comment_text
    result = await put_json(
        f"{GOKZ_TOP_V1}/maps/reviews",
        json_data={"map_id": maps[0]["id"], "steamid64": cd.steamid, "content": content},
        headers={"Authorization": f"Bearer {GOKZ_TOP_API_KEY}"} if GOKZ_TOP_API_KEY else None,
        timeout=30,
    )
    if not isinstance(result, dict) or result.get("detail"):
        return await rate.finish(f"提交评分失败: {result.get('detail', '请稍后再试。') if isinstance(result, dict) else '请稍后再试。'}")
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

    map_name, candidates = resolve_map_name(args_list[0])
    if candidates:
        return await comment.finish(map_selection_message(
            candidates,
            lambda selected: map_command("comment", selected, args_list[1]),
            event.get_user_id(),
        ))
    if not map_name:
        return await comment.finish("未找到该地图，请检查地图名是否正确。")

    maps = await fetch_json(f"{GOKZ_TOP_V1}/maps", params={"name": map_name, "limit": 1}, timeout=30)
    if not isinstance(maps, list) or not maps:
        return await comment.finish("未找到该地图，请检查地图名是否正确。")

    reviews = await fetch_json(
        f"{GOKZ_TOP_V1}/maps/reviews",
        params={"map_id": maps[0]["id"], "steamid64": cd.steamid, "limit": 1},
        timeout=30,
    )
    review_data = reviews.get("data") if isinstance(reviews, dict) else None
    existing_content = review_data[0].get("content") if isinstance(review_data, list) and review_data else None
    if not isinstance(existing_content, dict) or not isinstance(existing_content.get("overall"), int):
        return await comment.finish("请先使用 /rate 地图名 星级 评分，再使用 /comment 写评论。")

    result = await put_json(
        f"{GOKZ_TOP_V1}/maps/reviews",
        json_data={
            "map_id": maps[0]["id"],
            "steamid64": cd.steamid,
            "content": {**existing_content, "comment": args_list[1].strip()},
        },
        headers={"Authorization": f"Bearer {GOKZ_TOP_API_KEY}"} if GOKZ_TOP_API_KEY else None,
        timeout=30,
    )
    if not isinstance(result, dict) or result.get("detail"):
        detail = result.get("detail", "请稍后再试。") if isinstance(result, dict) else "请稍后再试。"
        return await comment.finish(f"提交评论失败: {detail}")
    await comment.finish(f"✅ 已为地图 {map_name} 提交评论。")


@kz.handle()
async def handle_kz(bot: Bot, event: Event, args: Message = CommandArg()):
    cd = CommandData(event, args)
    if cd.error:
        return await bot.send(event, cd.error)

    if cd.game == "cs2kz":
        await bot.send(event, "客服小祥正在为您: 生成CS2KZ资料页图片...")
        try:
            url = await cs2kz_screenshot_async(cd.steamid, force_update=cd.update)
        except Exception as exc:
            profile_url = f"https://cs2kz.org/profile/{cs2kz.cs2kz_player_id(cd.steamid)}"
            logger.warning(f"CS2KZ screenshot failed for {cd.steamid}: {exc!r}")
            return await bot.send(event, f"CS2KZ资料页截图生成失败，可直接查看:\n{profile_url}")
    elif cd.mode == "kz_vanilla":
        await bot.send(event, "客服小祥正在为您: 生成vnl-kz图片...")
        url = await vnl_screenshot_async(cd.steamid, force_update=cd.update)
    else:
        await bot.send(event, "客服小祥正在为您: 生成kzgo-eu图片...")
        url = await kzgoeu_screenshot_async(cd.steamid, cd.mode, force_update=cd.update)

    image_path = Path(url)
    if image_path.exists():
        await bot.send(event, MessageSegment.file_image(image_path))
    else:
        await bot.send(event, "图片生成失败，请稍后重试。")
