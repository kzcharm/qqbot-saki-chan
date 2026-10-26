from nonebot.adapters.qq import Message, MessageSegment
from nonebot.adapters.qq.models import MessageMarkdown

from src.plugins.gokz.core.keyboard import KeyboardBuilder


def mode_selection_message(current_mode: str) -> Message:
    """Build the GOKZ mode picker and its direct-submit QQ keyboard."""
    choices = ("OVR", "KZT", "SKZ", "VNL")
    content = (
        f"# 默认模式\n\n"
        f"当前模式：**{current_mode}**\n\n"
        "> 点击下方按钮即可切换默认模式。"
    )
    buttons = [
        KeyboardBuilder.button(
            id=f"mode_{label.lower()}",
            label=label,
            visited_label=f"已选择 {label}",
            style=1 if current_mode == label else 0,
            action_type=2,
            permission_type=2,
            action_data=f"/mode {label.lower()}",
            enter=True,
        )
        for label in choices
    ]
    return MessageSegment.markdown(MessageMarkdown(content=content)) + KeyboardBuilder.keyboard(buttons)
