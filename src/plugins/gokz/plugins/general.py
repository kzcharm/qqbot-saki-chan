from pathlib import Path
from textwrap import dedent

from nonebot.adapters.qq import Message, MessageEvent, MessageSegment
from nonebot.adapters.qq.models import MessageMarkdown
from nonebot.params import CommandArg
from src.plugins.gokz.core.binding_message import binding_help_message
from src.plugins.gokz.core.keyboard import KeyboardBuilder
from src.plugins.gokz.core.kreedz import format_kzmode
from src.plugins.gokz.core.mode_message import mode_selection_message
from src.plugins.gokz.core.profile import profile_markdown
from src.plugins.gokz.core.steam_user import convert_steamid

from ..application.models import CommandInput
from ..core.command_helper import CommandData
from ..presentation.qq_bridge import command_input, query
from ..presentation.qq_legacy import on_command

bind = on_command("bind", aliases={"绑定"})
mode = on_command("mode", aliases={"模式"})
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

    result = await query(profile, event, "profile", command_input(cd))
    data = result.data
    player_data = data["player"]
    links = data["links"]
    stats, jumpstats = data["stats"], data["jumpstats"]
    achievements, leaderboard = data["achievements"], data["rank"]
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
    
    result = await query(info, event, "info", command_input(cd))

    content = dedent(f"""
        昵称:             {result.data["account_name"]}
        steamID:      {convert_steamid(cd.steamid, 2)}
        steamID32:  {convert_steamid(cd.steamid, 32)}
        steamID64:  {convert_steamid(cd.steamid, 64)}
        默认模式:      {format_kzmode(cd.mode, form='m').upper()}
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

    result = await query(bind, event, "bind", CommandInput(arguments=(input_text,)))
    qq_name = result.data["name"]
    content = dedent(f"""
        绑定成功!
        {qq_name}
        {result.data["steamid"]}
    """).strip()
    # Add newline at start for group messages (bot will @ user automatically)
    if getattr(event, 'group_id', None):
        content = '\n' + content
    await bind.finish(content)


@mode.handle()
async def update_mode(event: MessageEvent, args: Message = CommandArg()):
    mode_ = args.extract_plain_text().strip()
    result = await query(mode, event, "mode", CommandInput(arguments=(mode_,) if mode_ else ()))
    await mode.finish(mode_selection_message(result.data["scope"]))
