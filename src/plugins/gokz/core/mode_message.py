from nonebot.adapters.qq import Message, MessageSegment
from nonebot.adapters.qq.models import MessageMarkdown

from src.plugins.gokz.core.keyboard import KeyboardBuilder


def mode_selection_message(game: str, current_mode: str) -> Message:
    """Build the Markdown game/mode picker and its direct-submit QQ keyboard."""
    choices = (
        ("OVR", "gokz", "ovr"),
        ("KZT", "gokz", "kzt"),
        ("SKZ", "gokz", "skz"),
        ("VNL", "gokz", "vnl"),
        ("CKZ (CS2)", "cs2kz", "classic"),
        ("VNL (CS2)", "cs2kz", "vanilla"),
    )
    game_label = "CS2KZ" if game == "cs2kz" else "GOKZ"

    content = (
        f"# 默认模式\n\n"
        f"当前游戏：**{game_label}**\n\n"
        f"当前模式：**{current_mode}**\n\n"
        "> 点击下方按钮即可切换游戏和默认模式。"
    )
    buttons = [
        KeyboardBuilder.button(
            id=f"mode_{choice_game}_{command}",
            label=label,
            visited_label=f"已选择 {label}",
            style=1 if game == choice_game and current_mode == ("CKZ" if command == "classic" else "VNL" if command == "vanilla" else command.upper()) else 0,
            action_type=2,
            permission_type=2,
            action_data=f"/mode {choice_game} {command}",
            enter=True,
        )
        for label, choice_game, command in choices
    ]
    return MessageSegment.markdown(MessageMarkdown(content=content)) + KeyboardBuilder.keyboard(
        buttons[:4], buttons[4:]
    )
