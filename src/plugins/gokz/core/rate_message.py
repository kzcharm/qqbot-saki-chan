from nonebot.adapters.qq import Message, MessageSegment
from nonebot.adapters.qq.models import MessageMarkdown

from src.plugins.gokz.core.keyboard import KeyboardBuilder


def rate_selection_message(map_name: str, current_rating: int | None = None) -> Message:
    """Build the one-tap map rating panel shown by ``/rate <map>``."""
    content = (
        f"# 为地图评分\n\n"
        f"地图：**{map_name}**\n\n"
        "> 点击星级即可提交总体评分；点击下方按钮可为已评分地图写评论。"
    )
    buttons = [
        KeyboardBuilder.button(
            id=f"rate_{stars}",
            label=f"{stars}⭐",
            visited_label="已提交",
            style=1 if stars == current_rating else 0,
            action_type=2,
            permission_type=2,
            action_data=f"/rate {map_name} {stars}",
            reply=True,
            enter=True,
        )
        for stars in range(1, 6)
    ]
    comment_button = KeyboardBuilder.button(
        id="rate_comment",
        label="写评论",
        visited_label="请输入评论",
        style=0,
        action_type=2,
        permission_type=2,
        action_data=f"/comment {map_name} ",
        reply=True,
        enter=False,
    )
    return MessageSegment.markdown(MessageMarkdown(content=content)) + KeyboardBuilder.keyboard(
        buttons, [comment_button]
    )
