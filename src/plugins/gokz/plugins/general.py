import json
from pathlib import Path
from textwrap import dedent

from nonebot import on_command, logger
from nonebot.adapters.qq import Bot, MessageEvent, Message, MessageSegment
from nonebot.params import CommandArg
from sqlalchemy.exc import NoResultFound
from sqlmodel import Session, select

from src.plugins.gokz.core.kreedz import format_kzmode
from src.plugins.gokz.core.game import format_cs2kz_mode, format_cs2kz_mode_label, format_game, toggle_game
from src.plugins.gokz.core.steam_user import convert_steamid
from src.plugins.gokz.core.binding_code import verify_binding_code
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
help_ = on_command('help', aliases={"帮助"})
info = on_command("info")


@info.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    cd = CommandData(event, args)
    if cd.error:
        if cd.error_image and cd.error_image.exists():
            return await info.finish(MessageSegment.file_image(cd.error_image) + MessageSegment.text(cd.error))
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


@bind.handle()
async def bind_steamid(event: MessageEvent, args: Message = CommandArg()):
    input_text = args.extract_plain_text().strip()
    image_path = Path('data/img/binding.png')
    
    if not input_text:
        if image_path.exists():
            return await bind.finish(
                MessageSegment.file_image(image_path)
                + MessageSegment.text("\n请在 gokz.top 生成绑定码后发送：/bind KZTOP...")
            )
        return await bind.finish("请在 gokz.top 生成绑定码后发送：/bind KZTOP...")

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
        请勿绑定他人的账号, 违者可能会被封禁
    """).strip()
    # Add newline at start for group messages (bot will @ user automatically)
    if getattr(event, 'group_id', None):
        content = '\n' + content
    await bind.finish(content)


@mode.handle()
async def update_mode(event: MessageEvent, args: Message = CommandArg()):
    mode_ = args.extract_plain_text()
    with Session(engine) as session:
        user = session.get(User, event.get_user_id())
    if not user:
        return await mode.finish("你还未绑定steamid")

    if not mode_:
        current = format_cs2kz_mode_label(user.cs2kz_mode) if user.game == "cs2kz" else format_kzmode(user.mode, "m").upper()
        return await mode.finish(f"当前模式为: {current}")

    try:
        mode_ = format_cs2kz_mode_label(mode_) if getattr(user, "game", "gokz") == "cs2kz" else format_kzmode(mode_, "m").upper()
    except ValueError:
        return await mode.finish("模式格式不正确")

    qid = event.get_user_id()
    with Session(engine) as session:
        user: User | None = session.get(User, qid)
        if not user:
            return await mode.finish("你还未绑定steamid")

        if user.game == "cs2kz":
            user.cs2kz_mode = mode_
        else:
            user.mode = mode_
        session.add(user)
        session.commit()
        session.refresh(user)

    await mode.finish(f"模式已更新为: {mode_}")


@game.handle()
async def update_game(event: MessageEvent, args: Message = CommandArg()):
    with Session(engine) as session:
        user = session.get(User, event.get_user_id())
        if not user:
            return await game.finish("你还未绑定steamid")
        try:
            selected_game = format_game(args.extract_plain_text()) if args.extract_plain_text() else toggle_game(user.game)
        except ValueError:
            return await game.finish("游戏格式不正确，可选: gokz | cs2kz")
        user.game = selected_game
        session.add(user)
        session.commit()
    await game.finish(f"默认游戏已更新为: {selected_game}")
