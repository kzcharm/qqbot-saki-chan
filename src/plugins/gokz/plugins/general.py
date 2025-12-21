import json
from pathlib import Path
from textwrap import dedent

from nonebot import on_command, logger
from nonebot.adapters.qq import Bot, MessageEvent, Message, MessageSegment
from nonebot.params import CommandArg
from sqlalchemy.exc import NoResultFound
from sqlmodel import Session, select

from src.plugins.gokz.core.kreedz import format_kzmode
from src.plugins.gokz.core.steam_user import convert_steamid
from src.plugins.gokz.core.binding_code import decode_binding_code
from src.plugins.gokz.config import QQ_BOT_SECRET, ENABLE_DIRECT_STEAM_BINDING
from ..api.helper import fetch_json
from ..core.command_helper import CommandData
from ..db.db import engine, create_db_and_tables
from ..db.models import User, Leaderboard

create_db_and_tables()


bind = on_command("bind", aliases={"绑定"})
mode = on_command("mode", aliases={"模式"})
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
        默认模式:      {format_kzmode(cd.mode, form='m').upper()}
        QID: {cd.qid}
    """).strip()
    await info.finish(content)


@help_.handle()
async def _():
    image_path = Path('data/gokz/help.png')
    await help_.finish(MessageSegment.file_image(image_path))


@bind.handle()
async def bind_steamid(event: MessageEvent, args: Message = CommandArg()):
    input_text = args.extract_plain_text()
    image_path = Path('data/img/binding.png')
    
    if not input_text:
        if image_path.exists():
            return await bind.finish(MessageSegment.file_image(image_path))
        else:
            if ENABLE_DIRECT_STEAM_BINDING:
                return await bind.finish("请输入绑定码或steamid")
            else:
                return await bind.finish("请输入绑定码")

    # Send binding image when user provides input
    if image_path.exists():
        await bind.send(MessageSegment.file_image(image_path))

    steamid = None
    binding_code_result = None

    # Try to decode as binding code first
    if len(input_text) == 32 and all(c.upper() in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ" for c in input_text):
        if not QQ_BOT_SECRET:
            return await bind.finish("绑定码功能未配置，请联系管理员")
        
        binding_code_result = decode_binding_code(input_text.upper(), QQ_BOT_SECRET)
        if binding_code_result:
            steamid = binding_code_result["steamid64"]
        elif not ENABLE_DIRECT_STEAM_BINDING:
            return await bind.finish("绑定码无效或已过期，请重新生成")
    
    # If binding code failed and direct binding is enabled, try direct SteamID
    if not steamid and ENABLE_DIRECT_STEAM_BINDING:
        try:
            steamid = convert_steamid(input_text)
        except ValueError:
            return await bind.finish("Steamid格式不正确")
    elif not steamid:
        return await bind.finish("绑定码无效或已过期，请重新生成")

    # 阻止他们绑定前20玩家的steamid
    top20 = json.load(open("data/gokz/json/top20_players.json"))
    for player in top20:
        if steamid == player["steamid"]:
            return await bind.finish(f"你是 {player['name']} 吗, 你就绑")

    user_id = event.get_user_id()
    is_binding_code = binding_code_result is not None
    
    # Get player name from gokz.top API
    player_url = f'https://api.gokz.top/api/v1/players/{steamid}'
    player_data = await fetch_json(player_url, timeout=10)
    qq_name = player_data.get("name", "Unknown") if player_data else "Unknown"

    with Session(engine) as session:
        # If using binding code, force bind by removing any existing binding
        if is_binding_code:
            try:
                statement = select(User).where(User.steamid == steamid)  # NOQA
                exist_user: User = session.exec(statement).one()
                # Delete the old user record to unbind
                session.delete(exist_user)
                session.commit()
            except NoResultFound:
                pass
        else:
            # For direct binding, check for duplicates
            try:
                statement = select(User).where(User.steamid == steamid)  # NOQA
                exist_user: User = session.exec(statement).one()
                return await bind.finish(f"该steamid已经被 {exist_user.name} QQ号{exist_user.qid} 绑定 ")
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

    await bind.finish(content)


@mode.handle()
async def update_mode(event: MessageEvent, args: Message = CommandArg()):
    if mode_ := args.extract_plain_text():
        try:
            mode_ = format_kzmode(mode_)
        except ValueError:
            return await mode.finish("模式格式不正确")
    else:
        return await mode.finish("你模式都不给我我怎么帮你改ヽ(ー_ー)ノ")

    qid = event.get_user_id()
    with Session(engine) as session:
        user: User | None = session.get(User, qid)
        if not user:
            return await mode.finish("你还未绑定steamid")

        user.mode = mode_
        session.add(user)
        session.commit()
        session.refresh(user)

    await mode.finish(f"模式已更新为: {mode_}")
