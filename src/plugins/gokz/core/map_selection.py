from collections.abc import Callable, Sequence

from nonebot.adapters.qq import Message, MessageSegment
from nonebot.adapters.qq.models import MessageMarkdown

from src.plugins.gokz.core.keyboard import KeyboardBuilder
from src.plugins.gokz.core.kreedz import search_map


MAX_MAP_CHOICES = 5


def map_command(command: str, map_name: str, *arguments: str) -> str:
    """Return a canonical QQ command with a selected map name."""
    return " ".join((f"/{command}", map_name, *(argument for argument in arguments if argument)))


def resolve_map_name(query: str) -> tuple[str | None, list[str]]:
    """Resolve a map query or return its ranked ambiguous candidates.

    Exact matches deliberately bypass the picker.  The second tuple item is
    empty for both an exact result and a query with no matches.
    """
    matches = search_map(query)
    if not matches:
        return None, []

    exact_match = next((name for name in matches if name.casefold() == query.casefold()), None)
    if exact_match is not None or len(matches) == 1:
        return exact_match or matches[0], []

    return None, matches[:MAX_MAP_CHOICES]


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
