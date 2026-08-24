from textwrap import dedent

from nonebot.adapters.qq import Message, MessageSegment
from nonebot.adapters.qq.models import MessageMarkdown

from src.plugins.gokz.core.keyboard import KeyboardBuilder


BINDING_CODE_URL = "https://gokz.top/settings/binding-code"


def binding_help_message() -> Message:
    """Build the shared Steam binding instructions and QQ action keyboard."""
    content = dedent(f"""
        # 绑定 Steam 账号

        1. [打开绑定页面]({BINDING_CODE_URL})，使用你的 Steam 账号登录。
        2. 在页面中点击“生成绑定码”。
        3. 复制绑定码并发送：`/bind KZTOP...`

        > 绑定码区分大小写，有效期为 5 分钟；过期或绑定失败时请重新生成。
    """).strip()
    keyboard = KeyboardBuilder.keyboard([
        KeyboardBuilder.button(
            id="binding_open_page",
            label="打开绑定页面",
            visited_label="已打开",
            style=1,
            action_type=0,
            permission_type=2,
            action_data=BINDING_CODE_URL,
            enter=False,
        ),
        KeyboardBuilder.button(
            id="binding_command",
            label="输入绑定命令",
            visited_label="请粘贴绑定码",
            style=0,
            action_type=2,
            permission_type=2,
            action_data="/bind ",
            enter=False,
        ),
    ])
    return MessageSegment.markdown(MessageMarkdown(content=content)) + keyboard
