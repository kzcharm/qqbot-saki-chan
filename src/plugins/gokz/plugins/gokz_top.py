import asyncio
from collections import Counter
from textwrap import dedent

from nonebot import on_command, logger
from nonebot.adapters.qq import MessageEvent as Event, Message
from nonebot.adapters.qq.models import MessageMarkdown
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from sqlmodel import Session

from src.plugins.gokz.core.command_helper import CommandData, parse_args
from src.plugins.gokz.core.formatter import diff_seconds_to_time, format_gruntime, record_format_time
from src.plugins.gokz.core.game import format_cs2kz_mode_label
from src.plugins.gokz.core.kreedz import format_kzmode
from src.plugins.gokz.core.map_selection import (
    map_command,
    map_selection_message,
    resolve_map_name,
)
from src.plugins.gokz.core.daily_map import get_daily_maps, utc_today
from src.plugins.gokz.core.daily_map_message import daily_map_message
from src.plugins.gokz.db.db import engine
from src.plugins.gokz.db.models import GroupServerSetting, User
from src.plugins.gokz.core.group_settings import (
    group_chat_id,
    group_info_markdown,
    set_server_target,
)
from src.plugins.gokz.core.server_status import (
    cn_server_group_choices,
    resolve_server_group_slug,
    server_group_status_markdown,
    server_groups_markdown,
)
from src.plugins.gokz.core.keyboard import KeyboardBuilder
from ..api import cs2kz
from ..api.gokz_top import GOKZTopAPIError, fetch_run_history
from ..api.helper import fetch_json
from nonebot.adapters.qq import MessageSegment

BASE = "https://api.gokz.top/v1"

progress = on_command('mp', aliases={'progress', '进度'})
ccf = on_command('ccf', aliases={'查成分'})
pk = on_command('pk', aliases={'pk'})
find = on_command('find', aliases={'查找'})
group_rank = on_command('群排名', aliases={'group_rank'}, permission=SUPERUSER)
daily = on_command('daily', aliases={'每日地图'})
server = on_command('server', aliases={'s', 'servers', 'serv'})
group_info = on_command('group_info')
set_server = on_command('set_server', permission=SUPERUSER)


@group_info.handle()
async def group_info_handle(event: Event):
    """Show the current QQ group ID and its configured default server group."""
    group_id = group_chat_id(event)
    if not group_id:
        return await group_info.finish("该命令只能在群聊中使用。")

    with Session(engine) as session:
        setting = session.get(GroupServerSetting, group_id)
    content = group_info_markdown(group_id, setting.server_group if setting else None)
    await group_info.finish(MessageSegment.markdown(MessageMarkdown(content=content)))


@set_server.handle()
async def set_server_handle(event: Event, args: Message = CommandArg()):
    """Set a group's default public server group for bare /server."""
    parsed_args = parse_args(args.extract_plain_text())
    target = set_server_target(parsed_args.get("args", ()), group_chat_id(event))
    if "error" in parsed_args or target is None:
        return await set_server.finish(
            "用法: /set_server <服务器组>\n"
            "或: /set_server <群组 ID> <服务器组>\n"
            "例如: /set_server axekz"
        )
    group_id, server_identifier = target

    response = await fetch_json(f"{BASE}/servers", params={"offset": 0, "limit": 200}, timeout=30)
    server_data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(server_data, list):
        return await set_server.finish("服务器状态暂时不可用，请稍后再试。")

    server_group = resolve_server_group_slug(server_data, server_identifier)
    if server_group is None:
        return await set_server.finish("未找到该服务器组，请使用 `/server` 查看可用服务器组。")

    with Session(engine) as session:
        setting = session.get(GroupServerSetting, group_id)
        if setting is None:
            session.add(GroupServerSetting(group_id=group_id, server_group=server_group))
        else:
            setting.server_group = server_group
            session.add(setting)
        session.commit()
    await set_server.finish(f"已将群组 `{group_id}` 的默认服务器组设为 `{server_group}`。")


@server.handle()
async def server_handle(event: Event, args: Message = CommandArg()):
    """Show public GOKZ.TOP server groups and their live text status."""
    parsed_args = parse_args(args.extract_plain_text())
    if "error" in parsed_args:
        return await server.finish("用法: /server [服务器组]\n例如: /server axekz")

    response = await fetch_json(f"{BASE}/servers", params={"offset": 0, "limit": 200}, timeout=30)
    server_data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(server_data, list):
        return await server.finish("服务器状态暂时不可用，请稍后再试。")

    group_identifier = " ".join(parsed_args["args"]).strip()
    if not group_identifier:
        group_id = group_chat_id(event)
        if group_id:
            with Session(engine) as session:
                setting = session.get(GroupServerSetting, group_id)
            group_identifier = setting.server_group if setting else ""
    if not group_identifier:
        content = server_groups_markdown(server_data)
        # QQ allows at most five keyboard rows. Two columns retain room for
        # every current CN group without reintroducing the row-limit error.
        buttons = [
            KeyboardBuilder.button(
                id=f"server_{slug}",
                label=name,
                visited_label="查看服务器",
                style=1,
                action_type=2,
                permission_type=2,
                action_data=f"/server {slug}",
                reply=True,
                enter=True,
            )
            for slug, name in cn_server_group_choices(server_data)[:10]
        ]
        message = MessageSegment.markdown(MessageMarkdown(content=content))
        if buttons:
            message += KeyboardBuilder.keyboard(
                *(buttons[index:index + 2] for index in range(0, len(buttons), 2))
            )
        return await server.finish(message)

    content = server_group_status_markdown(server_data, group_identifier)
    if content is None:
        content = "未找到可用的在线服务器组。\n\n" + server_groups_markdown(server_data)
        return await server.finish(MessageSegment.markdown(MessageMarkdown(content=content)))
    await server.finish(MessageSegment.markdown(MessageMarkdown(content=content)))


@daily.handle()
async def daily_map(event: Event, args: Message = CommandArg()):
    cd = CommandData(event, args)
    if cd.error:
        return await daily.finish(cd.error)
    if cd.game == "cs2kz":
        return await daily.finish("每日地图目前仅支持 GOKZ。")

    assignments = await get_daily_maps(cd.qid, cd.steamid, format_kzmode(cd.mode, "m").upper())
    if assignments is None:
        return await daily.finish("每日地图数据暂时不可用，请稍后再试。")

    await daily.finish(daily_map_message(assignments, utc_today()))


@find.handle()
async def find_handle(event: Event, args: Message = CommandArg()):
    parsed_args = parse_args(args.extract_plain_text())
    if "error" in parsed_args:
        return await find.finish(parsed_args["error"])
    name = " ".join(parsed_args["args"])
    with Session(engine) as session:
        user = session.get(User, event.get_user_id())
    game = parsed_args.get("game") or getattr(user, "game", "gokz")
    if name:
        if game == "cs2kz":
            players = await cs2kz.search_players(name)
            content = "════查找CS2KZ玩家════\n"
            content += "\n".join(
                f"{player['name']} | {player['id']} | CKZ {player.get('ckz_rating', 0):.0f} | VNL {player.get('vnl_rating', 0):.0f}"
                for player in players
            ) or "未找到该玩家"
            return await find.finish(content)
        players_data = await fetch_json(f"{BASE}/players/search", params={"q": name, "limit": 10})
        
        if players_data is None:
            return await find.finish("gokz-top API服务暂时不可用，请稍后再试。")
        
        # Check for error response (API returned non-200 with detail field)
        if isinstance(players_data, dict) and players_data.get('detail'):
            return await find.finish(players_data.get('detail'))
        
        try:
            players = players_data.get("data", [])
        except (KeyError, TypeError, AttributeError) as e:
            logger.error(f"Error parsing player data: {e}")
            return await find.finish("解析数据失败，请稍后再试。")

        content = '════查找玩家════\n'
        if not players:
            content += "未找到该玩家"
        for player in players:
            content += f"{player.get('alias') or player['name']} | {player['steamid64']}\n"
        # Add newline at start for group messages (bot will @ user automatically)
        if getattr(event, 'group_id', None):
            content = '\n' + content
        await find.send(content)
    else:
        await find.send("客服小祥提醒您: 请输入你要查找的玩家名")


@ccf.handle()
async def check_cheng_fen(event: Event, args: Message = CommandArg()):
    cd = CommandData(event, args)
    if cd.error:
        return await ccf.finish(cd.error)

    if cd.game == "cs2kz":
        records = await cs2kz.fetch_profile_records(cd.steamid, cd.mode)
        if not records:
            return await ccf.finish("未找到CS2KZ记录")
        counts = Counter(record["server"]["name"] for record in records)
        content = f"════CS2KZ成分查询════\n玩家:　{records[0]['player']['name']}\n模式:　{format_cs2kz_mode_label(cd.mode)}\n"
        content += "\n".join(f"{index}. {server} | {count}次 | ({count / len(records) * 100:.2f}%)" for index, (server, count) in enumerate(counts.most_common(10), 1))
        return await ccf.finish(content)

    preset_aliases = {
        'all': 'all',
        'pb': 'pb',
        'top': 'pb',
        'last_year': 'last_year',
        'year': 'last_year',
        'last_100_hours': 'last_100_hours',
        '100h': 'last_100_hours',
    }
    preset_names = {
        'all': '全部记录',
        'pb': '仅PB记录',
        'last_year': '最近一年',
        'last_100_hours': '最近100小时',
    }

    preset = 'all'
    if cd.args:
        preset = preset_aliases.get(cd.args[0].lower())
        if preset is None:
            return await ccf.finish("可选统计范围: all | pb | last_year | last_100_hours")

    url = f"{BASE}/players/{cd.steamid}/stats"
    records = await fetch_json(url)

    if records is None:
        return await ccf.finish("API服务暂时不可用，请稍后再试。")

    if isinstance(records, dict) and records.get('detail'):
        detail = records.get('detail')
        if isinstance(detail, list) and detail:
            detail = detail[0].get('msg', '请求参数错误')
        return await ccf.finish(str(detail))

    try:
        most_played = records.get('most_played_server', {}) if isinstance(records, dict) else {}
        periods = most_played.get('all_time', {}) if isinstance(most_played, dict) else {}
        groups = periods.get('entries', []) if isinstance(periods, dict) else []
        if not groups:
            return await ccf.finish("未找到该玩家的游玩记录。")

        total_hours = float(periods.get('total_seconds', 0)) / 3600
        current_preset_name = preset_names[preset]
        content = dedent(f"""
            ════成分查询════
            steamid: {records.get('steamid64', cd.steamid)}
            范围:　　{current_preset_name}
            总时长:　{total_hours:.2f}h
            ════════════
        """).strip() + '\n'
        for idx, group in enumerate(groups[:10]):
            group_name = group.get('label', '未知服务器组')
            playtime_hours = float(group.get('total_seconds', 0)) / 3600
            percentage = playtime_hours / total_hours * 100 if total_hours else 0
            content += f"{idx+1}. {group_name} | {playtime_hours:.2f}h | ({percentage:.2f}%)\n"
        # Add newline at start for group messages (bot will @ user automatically)
        if getattr(event, 'group_id', None):
            content = '\n' + content
        return await ccf.finish(content)
    except (KeyError, IndexError, TypeError, ValueError) as e:
        logger.error(f"Error processing records data: {e}")
        return await ccf.finish("解析数据失败，请稍后再试。")


@progress.handle()
async def map_progress(event: Event, args: Message = CommandArg()):
    cd = CommandData(event, args)
    if cd.error:
        return await progress.finish(cd.error)

    if not cd.args:
        return await progress.finish("🗺地图名都不给我怎么帮你查进度 (￣^￣) ")
    if cd.game == "cs2kz":
        map_data = await cs2kz.fetch_map(cd.args[0])
        if not map_data:
            return await progress.finish("未找到CS2KZ地图")
        map_name = map_data["name"]
        course = cs2kz.find_course(map_data, cd.course)
        data = await cs2kz.fetch_records(player=cd.steamid, map_name=map_name, course=course, mode=cd.mode, sort_order="ascending", limit=10000)
        if not data:
            return await progress.finish(f"你尚未完成过{map_name} - {course}")
        records = []
        for record in data:
            if not records or record["time"] < records[-1]["time"]:
                records.append(record)
        content = f"玩家: {data[0]['player']['name']}\n在地图: {map_name} - {course}\n模式: {format_cs2kz_mode_label(cd.mode)} 的进度\n"
        for record in reversed(records):
            content += f"╔ {format_gruntime(record['time'], True)} | {record['teleports']} TPs | #{cs2kz.record_rank(record) or '-'}\n"
        return await progress.finish(content)

    map_name, candidates = resolve_map_name(cd.args[0])
    if candidates:
        query_arguments = ("-m", str(format_kzmode(cd.mode, "m").upper()))
        if cd.steamid2:
            query_arguments += ("-s", cd.steamid)
        return await progress.finish(map_selection_message(
            candidates,
            lambda selected: map_command("mp", selected, *query_arguments),
            event.get_user_id(),
        ))
    if not map_name:
        return await progress.finish("未找到该地图")

    maps = await fetch_json(f"{BASE}/maps", params={"name": map_name, "limit": 10})
    if not isinstance(maps, list) or not maps:
        return await progress.finish(f"未找到地图 {map_name}")
    map_data = next((item for item in maps if item.get("name") == map_name), maps[0])

    scope = format_kzmode(cd.mode, "m").upper()
    histories = await asyncio.gather(
        fetch_run_history(cd.steamid, map_data["id"], scope, "NUB"),
        fetch_run_history(cd.steamid, map_data["id"], scope, "PRO"),
        return_exceptions=True,
    )
    nub_history, pro_history = histories
    if isinstance(nub_history, GOKZTopAPIError) and isinstance(pro_history, GOKZTopAPIError):
        return await progress.finish("GOKZ.TOP API服务暂时不可用，请稍后再试。")
    if isinstance(nub_history, GOKZTopAPIError):
        logger.warning("Unable to fetch NUB run history: %s", nub_history)
        nub_history = {"data": []}
    if isinstance(pro_history, GOKZTopAPIError):
        logger.warning("Unable to fetch PRO run history: %s", pro_history)
        pro_history = {"data": []}

    # NUB history includes every normal completion, including PRO runs.  Keep
    # only teleported runs here; the dedicated PRO history supplies zero-TP runs.
    nub_records = [record for record in nub_history.get("data", []) if record.get("teleports", 0) > 0]
    pro_records = [record for record in pro_history.get("data", []) if record.get("teleports", 0) == 0]
    if not nub_records and not pro_records:
        return await progress.finish(f"你尚未完成过{map_name}")

    try:
        content = f"玩家: {cd.steamid}\n在地图: {map_name}\n模式: {scope} 的进度\n"

        def personal_bests(records_):
            bests = []
            completions_since_pb = 0
            best_time = None
            for record_ in sorted(records_, key=lambda item: item["created_on"]):
                if best_time is None or record_["time"] < best_time:
                    bests.append((record_, completions_since_pb))
                    best_time = record_["time"]
                    completions_since_pb = 0
                else:
                    completions_since_pb += 1
            return list(reversed(bests))

        def generate_content(records_, title):
            content_ = f"====={title}=====\n"
            for i, (record_, completions_) in enumerate(records_):
                if i == len(records_) - 1:
                    time_diff = 0
                else:
                    time_diff = records_[i + 1][0]["time"] - record_["time"]
                content_ += f"╔ {format_gruntime(record_['time'], True)} (-{diff_seconds_to_time(time_diff)})\n"
                content_ += f"╠ {record_['teleports']} TPs\n"
                content_ += f"╚ {record_format_time(record_['created_on'])}\n"
                if i < len(records_) - 1 and records_[i][1] > 0:
                    content_ += f"--- {records_[i][1]} 次完成 ---\n"
            return content_

        if nub_records:
            content += generate_content(personal_bests(nub_records), "TP")
        if pro_records:
            content += generate_content(personal_bests(pro_records), "PRO")
        # Add newline at start for group messages (bot will @ user automatically)
        if getattr(event, 'group_id', None):
            content = '\n' + content
        await progress.finish(content)
    except (KeyError, IndexError, TypeError, ValueError) as e:
        logger.error(f"Error processing progress data: {e}")
        return await progress.finish("解析数据失败，请稍后再试。")
