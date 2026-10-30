from collections.abc import Callable, Sequence

from nonebot.adapters.qq import Message, MessageSegment
from nonebot.adapters.qq.models import MessageMarkdown

from src.plugins.gokz.core.keyboard import KeyboardBuilder
from src.plugins.gokz.core.map_lookup import resolve_map_name  # noqa: F401 - legacy import compatibility


MAX_MAP_CHOICES = 5


def map_command(command: str, map_name: str, *arguments: str) -> str:
    """Return a canonical QQ command with a selected map name."""
    return " ".join((f"/{command}", map_name, *(argument for argument in arguments if argument)))


def map_selection_message(
    candidates: Sequence[str],
    command_for_map: Callable[[str], str],
    user_id: str,
) -> Message:
    """Build the direct-submit QQ picker used for an ambiguous map query."""
    content = "# 请选择地图\n\n" \
        "> 找到多个可能的地图，请点击下方按钮继续查询。"
    buttons = [
        KeyboardBuilder.button(
            id=f"map_choice_{index}",
            label=map_name,
            visited_label="查询中",
            style=1,
            action_type=2,
            permission_type=0,
            action_data=command_for_map(map_name),
            specify_user_ids=[user_id],
            reply=True,
            enter=True,
        )
        for index, map_name in enumerate(candidates, 1)
    ]
    return MessageSegment.markdown(MessageMarkdown(content=content)) + KeyboardBuilder.keyboard(
        *([button] for button in buttons)
    )
