from textwrap import dedent

from nonebot import logger
from nonebot.adapters.qq import Message, MessageSegment
from nonebot.adapters.qq import MessageEvent as Event
from nonebot.adapters.qq.models import MessageMarkdown
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from src.plugins.gokz.core.command_helper import CommandData, parse_args
from src.plugins.gokz.core.daily_map_message import daily_map_message
from src.plugins.gokz.core.formatter import (
    diff_seconds_to_time,
    format_gruntime,
    record_format_time,
)
from src.plugins.gokz.core.group_settings import (
    group_chat_id,
    group_info_markdown,
    set_server_target,
)
from src.plugins.gokz.core.keyboard import KeyboardBuilder
from src.plugins.gokz.core.server_status import (
    cn_server_group_choices,
    server_group_status_markdown,
    server_groups_markdown,
)

from ..application.models import CommandInput
from ..presentation.qq_bridge import command_input, query
from ..presentation.qq_legacy import on_command

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

    result = await query(group_info, event, "group_info", CommandInput())
    content = group_info_markdown(group_id, result.data["default"] or None)
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

    result = await query(set_server, event, "set_server", CommandInput(arguments=(group_id, server_identifier)))
    server_group = result.data["default"]
    await set_server.finish(f"已将群组 `{group_id}` 的默认服务器组设为 `{server_group}`。")


@server.handle()
async def server_handle(event: Event, args: Message = CommandArg()):
    """Show public GOKZ.TOP server groups and their live text status."""
    parsed_args = parse_args(args.extract_plain_text())
    if "error" in parsed_args:
        return await server.finish("用法: /server [服务器组]\n例如: /server axekz")

    result = await query(server, event, "server", CommandInput(arguments=tuple(parsed_args["args"])))
    server_data = result.data["servers"]
    group_identifier = result.data["identifier"]
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

    result = await query(daily, event, "daily", command_input(cd))
    await daily.finish(daily_map_message(result.data["assignments"], result.data["date"]))


@find.handle()
async def find_handle(event: Event, args: Message = CommandArg()):
    parsed_args = parse_args(args.extract_plain_text())
    if "error" in parsed_args:
        return await find.finish(parsed_args["error"])
    name = " ".join(parsed_args["args"])
    if name:
        result = await query(find, event, "find", CommandInput(arguments=(name,)))
        players = result.data["players"]

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


    result = await query(ccf, event, "ccf", command_input(cd))
    records, preset = result.data["stats"], result.data["preset"]
    preset_names = {'all': '全部记录', 'pb': '仅PB记录', 'last_year': '最近一年', 'last_100_hours': '最近100小时'}

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

    result = await query(progress, event, "mp", command_input(cd), target=cd.steamid if cd.steamid2 else None)
    map_name, scope = result.data["map_name"], result.data["scope"]
    nub_records, pro_records = result.data["progress"]["NUB"], result.data["progress"]["PRO"]
    if not nub_records and not pro_records:
        return await progress.finish(f"你尚未完成过{map_name}")

    try:
        content = f"玩家: {cd.steamid}\n在地图: {map_name}\n模式: {scope} 的进度\n"

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
            content += generate_content(nub_records, "TP")
        if pro_records:
            content += generate_content(pro_records, "PRO")
        # Add newline at start for group messages (bot will @ user automatically)
        if getattr(event, 'group_id', None):
            content = '\n' + content
        await progress.finish(content)
    except (KeyError, IndexError, TypeError, ValueError) as e:
        logger.error(f"Error processing progress data: {e}")
        return await progress.finish("解析数据失败，请稍后再试。")
