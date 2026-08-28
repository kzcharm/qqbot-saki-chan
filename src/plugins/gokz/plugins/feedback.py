from nonebot import on_command
from nonebot.adapters.qq import MessageSegment
from nonebot.adapters.qq.models import MessageMarkdown

from src.plugins.gokz.core.keyboard import KeyboardBuilder


FEEDBACK_GROUP_URL = "https://qm.qq.com/q/c8P0TtgpIA"
FEEDBACK_QR_CODE_URL = "https://gokztop-1312466598.cos.ap-guangzhou.myqcloud.com/qrcode.png"

feedback = on_command("feedback")


def feedback_message():
    content = (
        "# 问题反馈\n\n"
        "遇到问题、发现 Bug 或有功能建议？\n"
        "欢迎加入反馈群\n\n"
        f"![GOKZ.TOP 反馈群二维码]({FEEDBACK_QR_CODE_URL})"
    )
    keyboard = KeyboardBuilder.keyboard([
        KeyboardBuilder.button(
            id="feedback_join_group",
            label="点击链接加入群聊【GOKZ.TOP】",
            visited_label="已打开加群链接",
            style=1,
            action_type=0,
            permission_type=2,
            action_data=FEEDBACK_GROUP_URL,
            enter=False,
            unsupport_tips="当前 QQ 客户端不支持打开群聊链接",
        )
    ])
    return MessageSegment.markdown(MessageMarkdown(content=content)) + keyboard


@feedback.handle()
async def handle_feedback():
    await feedback.finish(feedback_message())
