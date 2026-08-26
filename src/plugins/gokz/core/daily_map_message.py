"""QQ Markdown rendering for daily-map assignments."""

from __future__ import annotations

from datetime import date
import random
from typing import Mapping
from urllib.parse import quote

from nonebot.adapters.qq import Message, MessageSegment
from nonebot.adapters.qq.models import MessageMarkdown

from src.plugins.gokz.core.keyboard import KeyboardBuilder
from src.plugins.gokz.db.models import DailyMapAssignment


DAILY_INTROS = (
    "📅 {date} · 今日地图来咯！(๑•̀ㅂ•́)و✧",
    "今日份地图已刷新，看看今天跳啥？(⁎˃ᴗ˂⁎)",
    "🗓️ {date}，KZ启动！地图选好了，就等你来～",
    "今日地图准时送达！准备好你的空格和滚轮了吗？😼",
    "✨ 新的一天，新的图！{date} 今日地图请查收～",
    "起床第一句：今天跳哪张？答案来了！(•̀ᴗ•́)و ̑̑",
    "📍 今日地图定位成功！开荒+旧图，双倍快乐！",
    "{date} KZ日历：宜开荒，宜刷图，忌躺平～😤",
    "今天的图有点东西，{new_map_tier}+{old_map_tier}组合拳，接得住吗？💥",
    "每日一跳，烦恼丢掉！今日地图已就位～٩(ˊᗜˋ*)و",
    "🎮 打开CS，加载地图，今日KZ之旅开始！",
    "今日地图：新图开胃，旧图回味，完美搭配！🍽️",
    "听说今天有新图？还有老朋友？这不得冲？(ง •̀_•́)ง",
    "{date} 地图轮换已更新，来看看你的本命图在不在？",
    "🌟 今日地图推荐：一张练技术，一张练心态，齐活！",
    "滴！KZ打卡成功，今日地图请过目～(｡•̀ᴗ-)✧",
    "今天的地图包治各种手痒，{new_map_tier}新图+{old_map_tier}旧图，安排！",
    "不跳图的第N天…不行，今日地图已出，我要回归！😆",
    "{date} KZ菜单：前菜新图，主菜旧图，甜点是刷记录～",
    "今日地图加载中…请稍候…叮！开跳！(ノ°ο°)ノ",
)

NEW_MAP_INTROS = (
    "🗺️ 开荒新图 {new_map} {new_map_tier}！第一个通关的会是你吗？",
    "新图开荒！{new_map_tier}难度，小心别摔键盘哦～(´･ω･`)",
    "✨ 开荒新图：{new_map}，连跳大冒险开始！",
    "新图摸黑跳？别怕，死多了路就熟了！{new_map_tier}等你来盘！",
    "🌱 开荒新图 {new_map_tier}，每一步都是历史！快留下你的脚印～",
    "新图 {new_map} 上线！{new_map_tier}难度，敢不敢来试试？",
    "开荒时间到！这张{new_map_tier}新图能让你怀疑人生吗？😏",
    "🧭 新图开荒指南：多跳、多死、多记点，{new_map_tier}也变简单！",
    "{new_map} {new_map_tier} 开荒中！跳不过去就多练，别放弃！",
    "新图开荒最快乐的事：发现捷径！{new_map_tier}图里藏了多少？",
    "💥 {new_map_tier}新图来炸场！{new_map} 准备好被征服了吗？",
    "开荒新图就像开盲盒，{new_map_tier}可能是惊吓也可能是惊喜～😆",
    "新图 {new_map} {new_map_tier}：连跳党的福音，手残党的噩梦？",
    "🚀 开荒新图，冲就完事！{new_map_tier}难度，跳到起飞！",
    "今天的新图有点硬核，{new_map_tier} {new_map}，敢来挑战的都是勇士！",
    "新图开荒不迷路，跟着感觉跳！{new_map_tier} bhop 走起～(•̀ᴗ•́)و",
    "{new_map} {new_map_tier} 开荒队招募中！要求：不怕死，有耐心～",
    "新图第一跳由你开始！{new_map_tier} {new_map}，记录等你来写！",
    "🌟 开荒新图，把{new_map_tier}跳成T2就是你的终极目标！加油～",
    "{new_map_tier}新图开荒，建议带上护腕和好心态，我们图里见！",
)

IMPROVEMENT_MAP_INTROS = (
    "🔥 挑战旧图 {old_map} {old_map_tier}！老图新跳，手感还在吗？",
    "旧图回归！{old_map_tier} {old_map}，曾经的痛还记得吗？来复仇！",
    "💪 挑战旧图：{old_map}，刷个新纪录证明自己！",
    "老图不老的秘诀：每次跳都有新感觉！{old_map_tier} {old_map} 走起～",
    "🎯 旧图挑战赛！{old_map_tier} {old_map}，看谁是最速传说？",
    "这张{old_map_tier}旧图，当年卡了半小时，今天几把过？😤",
    "{old_map} {old_map_tier} 再次挑战！肌肉记忆唤醒中…",
    "旧图就像老朋友，{old_map_tier} {old_map} 今天也要好好“叙旧”～",
    "挑战旧图，找回初心！{old_map_tier} 难度，轻松中带着细节～",
    "🔄 旧图重刷，记录刷新！{old_map} {old_map_tier} 就等你来破！",
    "今天挑战旧图，{old_map_tier} {old_map} 不要小看，细节决定成败！",
    "曾几何时{old_map_tier}也是天堑，如今是不是如履平地？来试试！",
    "🏆 旧图挑战：{old_map} {old_map_tier}，全服最快是你吗？",
    "旧图刷起来就是亲切！{old_map_tier} {old_map}，跳完还能教萌新～",
    "挑战旧图 {old_map_tier}，不为别的，就为那份熟悉的手感！",
    "{old_map} {old_map_tier}，经典永流传，今天再来亿遍！",
    "旧图新跳，温故知新！{old_map_tier} {old_map} 里藏着多少回忆？",
    "💥 挑战旧图，把{old_map_tier}跳出T1的流畅感，你可以的！",
    "今天旧图专场！{old_map} {old_map_tier}，看看谁还在坚持～",
    "老图虐我千百遍，我待老图如初恋！{old_map_tier} {old_map} 冲！",
)

DAILY_OUTROS = (
    "🎯 今日份KZ安排完毕，开跳！(๑•̀ㅂ•́)و✧",
    "别犹豫了，服务器等你！GOGOGO～٩(ˊᗜˋ*)و",
    "地图选好了，队友呢？上号上号！😎",
    "今日KZ任务：跳完新图，刷完旧图，然后截图发群里！",
    "💪 不管是{new_map_tier}还是{old_map_tier}，跳完就是胜利！加油，KZ人！",
    "新图旧图都安排上了，就差一个你了！快来～",
    "跳完记得来报个到，今天你过图了吗？(•̀ᴗ•́)و",
    "所有地图已就绪，准备好空格键，我们出发！",
    "🚀 KZ启动！今天的目标：不摔键盘，快乐过图！",
    "今日地图套餐已上齐，请慢用～跳完记得好评哦！",
    "不管新图旧图，能跳过去就是好图！冲鸭！🦆",
    "服务器见！希望今天大家都能刷新自己的记录～",
    "键盘鼠标已就位，KZ之旅开始，今晚不跳不散！",
    "新图开荒+旧图挑战，今天又是充实的一天！(｡•̀ᴗ-)✧",
    "别看了，就是你，上号！今日地图已为你准备好～",
    "跳KZ一时爽，一直跳一直爽！今天也来亿把！",
    "🎮 加载地图，进入服务器，今日KZ，现在开始！",
    "祝大家今天跳图不卡点，连跳不断腿，过图如飞！",
    "收下这份今日地图，去征服它们吧！我们终点见！",
    "最后喊一句：KZ人，KZ魂，跳图都是人上人！😤✨",
)


def _map_url(map_name: str) -> str:
    return f"https://gokz.top/maps/{quote(map_name, safe='')}/maptop"


def _render_copy(template: str, assignment_date: date, assignments: Mapping[str, DailyMapAssignment]) -> str:
    new_map = assignments.get("new")
    old_map = assignments.get("improvement")
    return template.format(
        date=assignment_date.isoformat(),
        new_map=new_map.map_name if new_map else "暂无",
        new_map_tier=f"T{new_map.map_tier}" if new_map else "暂无",
        old_map=old_map.map_name if old_map else "暂无",
        old_map_tier=f"T{old_map.map_tier}" if old_map else "暂无",
    )


def daily_map_message(assignments: Mapping[str, DailyMapAssignment], assignment_date: date) -> Message:
    """Render the immutable daily-map pair and a button to retrieve it again."""
    lines = ["# 今日地图", "", _render_copy(random.choice(DAILY_INTROS), assignment_date, assignments), ""]
    for daily_type, label, empty_message, templates in (
        ("new", "开荒新图", "你已经完成了当前模式的所有可选地图。", NEW_MAP_INTROS),
        ("improvement", "挑战旧图", "暂无超过 30 天未刷新 PB 的可选地图。", IMPROVEMENT_MAP_INTROS),
    ):
        assignment = assignments.get(daily_type)
        lines.append(f"## {label}")
        if assignment:
            lines.extend((_render_copy(random.choice(templates), assignment_date, assignments), f"[{assignment.map_name}]({_map_url(assignment.map_name)}) · T{assignment.map_tier}"))
        else:
            lines.append(empty_message)
        lines.append("")

    lines.extend((_render_copy(random.choice(DAILY_OUTROS), assignment_date, assignments), ""))

    return MessageSegment.markdown(MessageMarkdown(content="\n".join(lines).rstrip())) + KeyboardBuilder.keyboard([
        KeyboardBuilder.button(
            id="daily_maps",
            label="查看我的今日地图",
            visited_label="查看我的今日地图",
            style=1,
            action_type=2,
            permission_type=2,
            action_data="/daily",
            enter=True,
        )
    ])
