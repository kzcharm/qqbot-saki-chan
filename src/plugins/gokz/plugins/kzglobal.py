import math
from datetime import datetime
from pathlib import Path
from textwrap import dedent
from zoneinfo import ZoneInfo

from nonebot import on_command, logger
from nonebot.adapters.qq import Bot, Event, Message, MessageSegment
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER

from ..api.kztimerglobal import fetch_personal_best, fetch_personal_recent, fetch_world_record, fetch_overall_world_record, fetch_personal_bans, \
    update_map_data
from ..api.helper import fetch_json, put_json, post_json
from src.plugins.gokz.core.command_helper import CommandData
from src.plugins.gokz.core.config import MAP_TIERS
from src.plugins.gokz.core.formatter import format_gruntime, record_format_time
from src.plugins.gokz.core.kreedz import search_map
from src.plugins.gokz.core.kz.screenshot import vnl_screenshot_async, kzgoeu_screenshot_async
from src.plugins.gokz.core.map_img_url import get_map_img_url
from ..config import GOKZ_TOP_API_KEY

pb = on_command('pb', aliases={'personal-best'})
pr = on_command('pr')
kz = on_command('kz', aliases={'kzgo'})
wr = on_command('wr')
ban_ = on_command('ban')
rank = on_command('rank')
review = on_command('review', aliases={'评价', '评论'})
rate = on_command('rate', aliases={'评分', '评价地图'})
update_map_info = on_command('update_map', permission=SUPERUSER)

private_map_names: dict[int, str] = {}  # For private messages
group_map_names: dict[int, str] = {}  # For group messages

DEFAULT_MAP = 'bkz_cakewalk'


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
        if cd.error_image and cd.error_image.exists():
            return await ban_.send(MessageSegment.file_image(cd.error_image) + MessageSegment.text(cd.error))
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
        if cd.error_image and cd.error_image.exists():
            return await wr.finish(MessageSegment.file_image(cd.error_image) + MessageSegment.text(cd.error))
        return await wr.finish(cd.error)

    if not cd.args:
        return await wr.finish("🗺地图名都不给我怎么帮你查WR (￣^￣) ")
    else:
        map_name = search_map(cd.args[0])[0]

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
    combined_message = MessageSegment.file_image(img_path) + MessageSegment.text(content)
    await wr.send(combined_message)

    # if map_name == 'kz_hb_fafnir':
    #     await wr.send(MessageSegment.file_audio(Path('data/gokz/sound/fafnir.silk')))


@pr.handle()
async def handle_pr(bot: Bot, event: Event, args: Message = CommandArg()):
    cd = CommandData(event, args)
    if cd.error:
        if cd.error_image and cd.error_image.exists():
            return await pr.finish(MessageSegment.file_image(cd.error_image) + MessageSegment.text(cd.error))
        return await pr.finish(cd.error)

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
    combined_message = MessageSegment.file_image(img_path) + MessageSegment.text(content)

    await bot.send(event, combined_message)


@pb.handle()
async def map_pb(bot: Bot, event: Event, args: Message = CommandArg()):
    cd = CommandData(event, args)
    if cd.error:
        if cd.error_image and cd.error_image.exists():
            return await pb.finish(MessageSegment.file_image(cd.error_image) + MessageSegment.text(cd.error))
        return await pb.finish(cd.error)

    if not cd.args:
        return await wr.finish("🗺地图名都不给我怎么帮你查PB (￣^￣) ")
    else:
        map_name = search_map(cd.args[0])[0]

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

    img_path = await get_map_img_url(map_name)
    # Add newline at start for group messages (bot will @ user automatically)
    if getattr(event, 'group_id', None):
        content = '\n' + content
    combined_message = MessageSegment.file_image(img_path) + MessageSegment.text(content)

    await bot.send(event, combined_message)


@rank.handle()
async def handle_rank(bot: Bot, event: Event, args: Message = CommandArg()):
    cd = CommandData(event, args)
    if cd.error:
        if cd.error_image and cd.error_image.exists():
            return await rank.finish(MessageSegment.file_image(cd.error_image) + MessageSegment.text(cd.error))
        return await rank.finish(cd.error)

    BASE_URL = "https://api.gokz.top/api/v1"
    leaderboard_url = f"{BASE_URL}/leaderboards/{cd.steamid}"
    player_url = f"{BASE_URL}/players/{cd.steamid}"
    
    # Prepare headers with API key if available
    headers = {}
    if GOKZ_TOP_API_KEY:
        headers["Authorization"] = f"Bearer {GOKZ_TOP_API_KEY}"
    
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
        # PUT uses mode=kz_timer format
        params = {"mode": cd.mode}
        rank_data = await put_json(leaderboard_url, params=params, timeout=30, headers=headers)
        if rank_data is None:
            return await rank.finish("gokz-top API服务暂时不可用，请稍后再试。")
        
        # Check for error response (API returned non-200 with detail field)
        if isinstance(rank_data, dict) and rank_data.get('detail'):
            return await rank.finish(rank_data.get('detail'))
        
        # Check if response is not a valid success response (missing required fields)
        if not isinstance(rank_data, dict) or 'steamid64' not in rank_data:
            return await rank.finish("gokz-top API返回了无效数据，请稍后再试。")
        
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
        # Use GET request for normal query with KZT format
        # Convert mode to API format: kz_timer -> KZT, kz_simple -> SKZ, kz_vanilla -> VNL
        mode_mapping = {
            "kz_timer": "KZT",
            "kz_simple": "SKZ",
            "kz_vanilla": "VNL"
        }
        api_mode = mode_mapping.get(cd.mode, cd.mode.upper())
        params = {"mode": api_mode}
        rank_data = await fetch_json(leaderboard_url, params=params, timeout=30, headers=headers)
        if rank_data is None:
            return await rank.finish("gokz-top API服务暂时不可用，请稍后再试。")
        
        # Check for error response (API returned non-200 with detail field)
        if isinstance(rank_data, dict) and rank_data.get('detail'):
            return await rank.finish(rank_data.get('detail'))
        
        # Check if response is not a valid success response (missing required fields)
        if not isinstance(rank_data, dict) or 'steamid64' not in rank_data:
            return await rank.finish("gokz-top API返回了无效数据，请稍后再试。")
        
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
    
    map_search_results = search_map(args.extract_plain_text().strip())
    if not map_search_results:
        return await review.finish("未找到该地图，请检查地图名是否正确。")
    
    map_name = map_search_results[0]
    
    BASE_URL = "https://api.gokz.top/api/v1"
    
    # Prepare headers with API key if available
    headers = {}
    if GOKZ_TOP_API_KEY:
        headers["Authorization"] = f"Bearer {GOKZ_TOP_API_KEY}"
    
    # Fetch review summary
    summary_url = f"{BASE_URL}/maps/reviews/summary"
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
    
    summary = summary_list[0]
    stars = summary.get('stars', {})
    
    # Safely get star values, handling None
    overall_avg = stars.get('overall_avg_stars') or 0
    overall_count = stars.get('overall_count') or 0
    visuals_avg = stars.get('visuals_avg_stars') or 0
    visuals_count = stars.get('visuals_count') or 0
    gameplay_avg = stars.get('gameplay_avg_stars') or 0
    gameplay_count = stars.get('gameplay_count') or 0
    comment_count = summary.get('comment_count') or 0
    
    # Fetch map data to get authors
    map_url = f"{BASE_URL}/maps/name/{map_name}"
    map_data = await fetch_json(map_url, headers=headers, timeout=30)
    
    # Format author names (use alias if available, otherwise name)
    author_names = []
    if map_data and isinstance(map_data, dict):
        authors = map_data.get('authors', [])
        for author in authors:
            author_name = author.get('alias') or author.get('name', '未知作者')
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
    comments_url = f"{BASE_URL}/maps/{map_name}/comments"
    comments_params = {"offset": 0, "limit": 100, "include_ratings_only": "false"}
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
                player_name = comment_item.get('player_name', '未知玩家')
                comment_text = comment_item.get('comment', '')
                
                # Get overall rating from ratings array
                overall_rating = None
                ratings = comment_item.get('ratings', [])
                for rating in ratings:
                    if rating.get('aspect') == 'overall':
                        overall_rating = rating.get('rating')
                        break
                
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
        if cd.error_image and cd.error_image.exists():
            return await rate.finish(MessageSegment.file_image(cd.error_image) + MessageSegment.text(cd.error))
        return await rate.finish(cd.error)
    
    if not args:
        return await rate.finish("🗺地图名都不给我怎么帮你评分 (￣^￣) ")
    
    # Parse arguments
    args_text = args.extract_plain_text().strip()
    args_list = args_text.split()
    
    if len(args_list) < 2:
        return await rate.finish("用法: /rate map_name overall_star [comments]\n或: /rate map_name overall_star gameplay_star visual_star [comments]\n或: /rate map_name comments")
    
    # Search for map name
    map_search_results = search_map(args_list[0])
    if not map_search_results:
        return await rate.finish("未找到该地图，请检查地图名是否正确。")
    
    map_name = map_search_results[0]
    
    BASE_URL = "https://api.gokz.top/api/v1"
    
    # Prepare headers with API key if available
    headers = {}
    if GOKZ_TOP_API_KEY:
        headers["Authorization"] = f"Bearer {GOKZ_TOP_API_KEY}"
    
    params = {"steamid64": cd.steamid}
    
    # Check if first param after map name is an integer (rating) or text (comments only)
    try:
        overall_star = int(args_list[1])
        if not (1 <= overall_star <= 5):
            return await rate.finish("评分必须在1-5之间")
        
        # First param is a valid rating, proceed with rating logic
        # Check if 3 separate ratings are provided
        gameplay_star = None
        visual_star = None
        comments = None
        
        if len(args_list) >= 4:
            # Try to parse as 3 separate ratings
            try:
                gameplay_star = int(args_list[2])
                visual_star = int(args_list[3])
                if not (1 <= gameplay_star <= 5) or not (1 <= visual_star <= 5):
                    return await rate.finish("评分必须在1-5之间")
                # Comments start from index 4
                if len(args_list) > 4:
                    comments = ' '.join(args_list[4:])
            except ValueError:
                # If parsing fails, treat as comments
                comments = ' '.join(args_list[2:])
        elif len(args_list) > 2:
            # Comments provided with single rating
            comments = ' '.join(args_list[2:])
        
        # Submit ratings
        ratings_url = f"{BASE_URL}/maps/{map_name}/ratings"
        
        # Submit overall rating
        overall_data = {"aspect": "overall", "rating": overall_star}
        success, overall_result, error_msg = await post_json(ratings_url, json_data=overall_data, params=params, headers=headers, timeout=30)
        
        if not success:
            if error_msg:
                return await rate.finish(f"提交评分失败: {error_msg}")
            return await rate.finish("提交评分失败，请稍后再试。")
        
        # Submit gameplay and visuals ratings if provided
        if gameplay_star is not None:
            gameplay_data = {"aspect": "gameplay", "rating": gameplay_star}
            success, gameplay_result, error_msg = await post_json(ratings_url, json_data=gameplay_data, params=params, headers=headers, timeout=30)
            if not success:
                if error_msg:
                    logger.warning(f"Failed to submit gameplay rating for {map_name}: {error_msg}")
                else:
                    logger.warning(f"Failed to submit gameplay rating for {map_name}")
        
        if visual_star is not None:
            visual_data = {"aspect": "visuals", "rating": visual_star}
            success, visual_result, error_msg = await post_json(ratings_url, json_data=visual_data, params=params, headers=headers, timeout=30)
            if not success:
                if error_msg:
                    logger.warning(f"Failed to submit visuals rating for {map_name}: {error_msg}")
                else:
                    logger.warning(f"Failed to submit visuals rating for {map_name}")
        
        # Submit comment if provided
        if comments:
            comments_url = f"{BASE_URL}/maps/{map_name}/comments"
            comment_data = {"comment": comments}
            success, comment_result, error_msg = await post_json(comments_url, json_data=comment_data, params=params, headers=headers, timeout=30)
            if not success:
                if error_msg:
                    logger.warning(f"Failed to submit comment for {map_name}: {error_msg}")
                else:
                    logger.warning(f"Failed to submit comment for {map_name}")
        
        # Build success message
        content = f"✅ 已成功为地图 {map_name} 评分:\n"
        content += f"总体评分: {overall_star}⭐\n"
        
        if gameplay_star is not None:
            content += f"玩法评分: {gameplay_star}⭐\n"
        if visual_star is not None:
            content += f"视觉评分: {visual_star}⭐\n"
        if comments:
            content += f"评论: {comments}"
        
    except ValueError:
        # First param is not an integer, treat everything after map name as comments only
        comments = ' '.join(args_list[1:])
        
        if not comments:
            return await rate.finish("请提供评分或评论")
        
        # Submit comment only
        comments_url = f"{BASE_URL}/maps/{map_name}/comments"
        comment_data = {"comment": comments}
        success, comment_result, error_msg = await post_json(comments_url, json_data=comment_data, params=params, headers=headers, timeout=30)
        
        if not success:
            if error_msg:
                return await rate.finish(f"提交评论失败: {error_msg}")
            return await rate.finish("提交评论失败，请稍后再试。")
        
        # Build success message for comments only
        content = f"✅ 已成功为地图 {map_name} 添加评论:\n"
        content += f"评论: {comments}"
    
    # Add newline at start for group messages
    if getattr(event, 'group_id', None):
        content = '\n' + content
    
    await rate.finish(content)


@kz.handle()
async def handle_kz(bot: Bot, event: Event, args: Message = CommandArg()):
    cd = CommandData(event, args)
    if cd.error:
        if cd.error_image and cd.error_image.exists():
            return await bot.send(event, MessageSegment.file_image(cd.error_image) + MessageSegment.text(cd.error))
        return await bot.send(event, cd.error)

    if cd.mode == "kz_vanilla":
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
