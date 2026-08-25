from collections.abc import Callable, Sequence
from difflib import SequenceMatcher

from nonebot.adapters.qq import Message, MessageSegment
from nonebot.adapters.qq.models import MessageMarkdown

from src.plugins.gokz.core.keyboard import KeyboardBuilder
from src.plugins.gokz.core.kreedz import search_map


MAX_MAP_CHOICES = 5
_STRONG_MATCH_MIN_SCORE = 0.9
_STRONG_MATCH_GAP = 0.1


def _map_basename(map_name: str) -> str:
    """Return the map name without its mode/source prefix."""
    return map_name.split("_", 1)[1] if "_" in map_name else map_name


def map_command(command: str, map_name: str, *arguments: str) -> str:
    """Return a canonical QQ command with a selected map name."""
    return " ".join((f"/{command}", map_name, *(argument for argument in arguments if argument)))


def resolve_map_name(query: str) -> tuple[str | None, list[str]]:
    """Resolve a map query or return its ranked ambiguous candidates.

    Exact full-name and unique prefix-stripped matches bypass the picker.
    Strong fuzzy leaders are also selected directly; otherwise the second
    tuple item contains the ranked candidates for the picker.
    """
    matches = search_map(query)
    if not matches:
        return None, []

    normalized_query = query.casefold().strip()

    exact_match = next((name for name in matches if name.casefold() == normalized_query), None)
    if exact_match is not None or len(matches) == 1:
        return exact_match or matches[0], []

    # Users commonly omit the mode/source prefix (for example, ``sewer`` for
    # ``vnl_sewer``).  Treat a unique exact basename as an exact match too.
    basename_matches = [
        name for name in matches if _map_basename(name).casefold() == normalized_query
    ]
    if len(basename_matches) == 1:
        return basename_matches[0], []
    if basename_matches:
        return None, basename_matches[:MAX_MAP_CHOICES]

    # ``search_map`` may return fuzzy matches padded with weak alternatives.
    # Compare the user query with the basename so a typo such as ``lionhert``
    # prioritizes ``kz_lionheart`` over unrelated maps.  If the leader is
    # clearly ahead, either select it directly or keep only the close leaders.
    ranked = sorted(
        matches,
        key=lambda name: SequenceMatcher(
            None, normalized_query, _map_basename(name).casefold()
        ).ratio(),
        reverse=True,
    )
    scores = [
        SequenceMatcher(None, normalized_query, _map_basename(name).casefold()).ratio()
        for name in ranked
    ]
    if scores and scores[0] >= _STRONG_MATCH_MIN_SCORE:
        if len(scores) == 1 or scores[0] - scores[1] >= _STRONG_MATCH_GAP:
            return ranked[0], []
        strong = [
            name
            for name, score in zip(ranked, scores)
            if score >= scores[0] - _STRONG_MATCH_GAP
        ]
        if strong:
            return None, strong[:MAX_MAP_CHOICES]

    return None, ranked[:MAX_MAP_CHOICES]


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
