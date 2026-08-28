import asyncio
import json
from pathlib import Path
from textwrap import dedent

from nonebot import on_command, logger
from nonebot.adapters.qq import Bot, MessageEvent, Message, MessageSegment
from nonebot.adapters.qq.models import MessageMarkdown
from nonebot.params import CommandArg
from sqlalchemy.exc import NoResultFound
from sqlmodel import Session, select

from src.plugins.gokz.core.kreedz import format_kzmode
from src.plugins.gokz.core.game import format_cs2kz_mode, format_cs2kz_mode_label, format_game, toggle_game
from src.plugins.gokz.core.steam_user import convert_steamid
from src.plugins.gokz.core.binding_code import verify_binding_code
from src.plugins.gokz.core.binding_message import binding_help_message
from src.plugins.gokz.core.profile import profile_markdown
from src.plugins.gokz.core.mode_message import mode_selection_message
from src.plugins.gokz.core.keyboard import KeyboardBuilder
from src.plugins.gokz.config import QQ_BOT_SECRET
from ..api.helper import fetch_json
from ..core.command_helper import CommandData
from ..db.db import engine, create_db_and_tables
from ..db.models import User

create_db_and_tables()


bind = on_command("bind", aliases={"绑定"})
mode = on_command("mode", aliases={"模式"})
game = on_command("game", aliases={"游戏"})
test = on_command("test")
markdown_test = on_command("markdown_test", aliases={"测试Markdown"})
help_ = on_command('help', aliases={"帮助"})
info = on_command("info")
profile = on_command("profile", aliases={"资料"})

GOKZ_TOP_V1 = "https://api.gokz.top/v1"
TEST_IMAGE_URLS = (
    (
        "bkz_apricity_v3",
        "https://gokztop-1312466598.cos.ap-guangzhou.myqcloud.com/map-images/bkz_apricity_v3.webp",
    ),
)


@profile.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """Show a GOKZ.TOP player overview and their verified public links."""
    cd = CommandData(event, args)
    if cd.error:
        return await profile.finish(cd.error)

    player_url = f"{GOKZ_TOP_V1}/players/{cd.steamid}"
    social_links_url = f"{player_url}/social-links"
    player_data, social_links = await asyncio.gather(
        fetch_json(player_url, timeout=30),
        fetch_json(social_links_url, timeout=30),
    )
    if not isinstance(player_data, dict) or player_data.get("detail") or not player_data.get("steamid64"):
        return await profile.finish("未找到 GOKZ.TOP 玩家资料，或 API 暂时不可用，请稍后再试。")

    scope = player_data.get("primary_scope") or player_data.get("primary_mode")
    stats, jumpstats, achievements, leaderboard = await asyncio.gather(
        fetch_json(f"{player_url}/stats", timeout=30),
        fetch_json(f"{player_url}/jumpstats", params={"type": "LJ", "limit": 1, "sort_by": "distance", "sort_order": "desc"}, timeout=30),
        fetch_json(f"{player_url}/tournament-achievements", timeout=30),
        fetch_json(f"{GOKZ_TOP_V1}/leaderboards/players/{cd.steamid}", params={"scope": scope} if scope else None, timeout=30),
    )
    links = social_links if isinstance(social_links, list) else []
    content = profile_markdown(
        player_data,
        links,
        stats=stats if isinstance(stats, dict) else None,
        jumpstats=jumpstats if isinstance(jumpstats, dict) else None,
        achievements=achievements if isinstance(achievements, dict) else None,
        leaderboard=leaderboard if isinstance(leaderboard, dict) and not leaderboard.get("detail") else None,
    )
    await profile.finish(MessageSegment.markdown(MessageMarkdown(content=content)))


@info.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    cd = CommandData(event, args)
    if cd.error:
        return await info.finish(cd.error)
    
    with Session(engine) as session:
        statement = select(User).where(User.qid == cd.qid)  # NOQA
        user: User = session.exec(statement).one()

    content = dedent(f"""
        昵称:             {user.name}
        steamID:      {convert_steamid(cd.steamid, 2)}
        steamID32:  {convert_steamid(cd.steamid, 32)}
        steamID64:  {convert_steamid(cd.steamid, 64)}
        默认模式:      {format_cs2kz_mode_label(cd.mode) if cd.game == "cs2kz" else format_kzmode(cd.mode, form='m').upper()}
        QID: {cd.qid}
    """).strip()
    # Add newline at start for group messages (bot will @ user automatically)
    if getattr(event, 'group_id', None):
        content = '\n' + content
    await info.finish(content)


@help_.handle()
async def _():
    image_path = Path('data/gokz/help.png')
    await help_.finish(MessageSegment.file_image(image_path))


@markdown_test.handle()
async def _():
    """Send a representative custom Markdown message for QQ rendering checks."""
    content = dedent("""
        # Markdown 消息测试
        ## QQ 机器人

        **加粗**、_斜体_、~~删除线~~、__下划线加粗__

        [打开 gokz.top](https://gokz.top)
        <https://bot.q.qq.com>

        1. 有序列表第一项
        2. 有序列表第二项

        - 无序列表第一项
        - 无序列表第二项

        > 这是一条引用文本

        ***
        测试完成。
    """).strip()
    await markdown_test.finish(MessageSegment.markdown(MessageMarkdown(content=content)))


@test.handle()
async def _():
    """Try an AXE R2-hosted Markdown image with an action keyboard."""

    def build_test_message(image_name: str, image_url: str) -> Message:
        content = dedent(f"""
            # Markdown 图片与键盘测试

            ![{image_name}]({image_url})

            图片：**{image_name}**

            > 如果图片未显示，说明当前地址或 QQ Markdown 图片抓取不兼容。
        """).strip()
        keyboard = KeyboardBuilder.keyboard([
            KeyboardBuilder.button(
                id="test_open_image",
                label="打开测试图片",
                visited_label="已打开",
                style=1,
                action_type=0,
                permission_type=2,
                action_data=image_url,
                enter=False,
            ),
            KeyboardBuilder.button(
                id="test_again",
                label="再次测试",
                visited_label="已测试",
                style=0,
                action_type=2,
                permission_type=2,
                action_data="/test",
                enter=True,
            ),
        ])
        return MessageSegment.markdown(MessageMarkdown(content=content)) + keyboard

    for image_name, image_url in TEST_IMAGE_URLS[:-1]:
        await test.send(build_test_message(image_name, image_url))
    image_name, image_url = TEST_IMAGE_URLS[-1]
    await test.finish(build_test_message(image_name, image_url))


@bind.handle()
async def bind_steamid(event: MessageEvent, args: Message = CommandArg()):
    input_text = args.extract_plain_text().strip()
    
    if not input_text:
        return await bind.finish(binding_help_message())

    if not QQ_BOT_SECRET:
        return await bind.finish("绑定码功能未配置，请联系管理员")

    try:
        binding_code_result = verify_binding_code(input_text, QQ_BOT_SECRET)
    except ValueError:
        return await bind.finish("绑定码无效或已过期，请重新生成")

    steamid = binding_code_result["steamid64"]

    # 阻止他们绑定前20玩家的steamid
    top20 = json.load(open("data/gokz/json/top20_players.json"))
    for player in top20:
        if steamid == convert_steamid(player.get("steamid64") or player["steamid"], 64):
            return await bind.finish(f"你是 {player['name']} 吗, 你就绑")
    # Validate the player and use the GOKZ profile name for the binding.
    player_url = f'https://api.gokz.top/v1/players/{steamid}'
    player_data = await fetch_json(player_url, timeout=10)
    qq_name = player_data.get("name") if isinstance(player_data, dict) else None
    if not qq_name:
        return await bind.finish("用户不存在. 你至少上传过一次GOKZ记录吗?\n(最近才入坑的玩家绑不上是正常的)")

    user_id = event.get_user_id()
    with Session(engine) as session:
        # A verified code proves account ownership, so it may transfer an
        # existing Steam binding to the QQ user presenting the code.
        try:
            statement = select(User).where(User.steamid == steamid)  # NOQA
            exist_user: User = session.exec(statement).one()
            session.delete(exist_user)
            session.commit()
        except NoResultFound:
            pass

        user = session.get(User, user_id)
        if user:
            user.name = qq_name
            user.steamid = steamid
        else:
            user = User(qid=user_id, name=qq_name, steamid=steamid)
            session.add(user)
        session.commit()
        session.refresh(user)

    content = dedent(f"""
        绑定成功!
        {qq_name}
        {user.steamid}
    """).strip()
    # Add newline at start for group messages (bot will @ user automatically)
    if getattr(event, 'group_id', None):
        content = '\n' + content
    await bind.finish(content)


@mode.handle()
async def update_mode(event: MessageEvent, args: Message = CommandArg()):
    mode_ = args.extract_plain_text().strip()
    with Session(engine) as session:
        user = session.get(User, event.get_user_id())
    if not user:
        return await mode.finish(binding_help_message())

    if not mode_:
        current = format_cs2kz_mode_label(user.cs2kz_mode) if user.game == "cs2kz" else format_kzmode(user.mode, "m").upper()
        return await mode.finish(mode_selection_message(user.game, current))

    selected_game = user.game
    parts = mode_.split(maxsplit=1)
    if len(parts) == 2 and parts[0].lower() in {"gokz", "cs2kz"}:
        selected_game, mode_ = parts[0].lower(), parts[1]

    try:
        mode_ = format_cs2kz_mode_label(mode_) if selected_game == "cs2kz" else format_kzmode(mode_, "m").upper()
    except ValueError:
        return await mode.finish("模式格式不正确")

    qid = event.get_user_id()
    with Session(engine) as session:
        user: User | None = session.get(User, qid)
        if not user:
            return await mode.finish(binding_help_message())

        user.game = selected_game
        if selected_game == "cs2kz":
            user.cs2kz_mode = mode_
        else:
            user.mode = mode_
        session.add(user)
        session.commit()
        session.refresh(user)

    await mode.finish(mode_selection_message(selected_game, mode_))


@game.handle()
async def update_game(event: MessageEvent, args: Message = CommandArg()):
    with Session(engine) as session:
        user = session.get(User, event.get_user_id())
        if not user:
            return await game.finish(binding_help_message())
        try:
            selected_game = format_game(args.extract_plain_text()) if args.extract_plain_text() else toggle_game(user.game)
        except ValueError:
            return await game.finish("游戏格式不正确，可选: gokz | cs2kz")
        user.game = selected_game
        session.add(user)
        session.commit()
    await game.finish(f"默认游戏已更新为: {selected_game}")
