"""Chinese QQ Markdown with direct-submit keyboards."""

import shlex

from nonebot.adapters.qq import MessageSegment
from nonebot.adapters.qq.models import MessageMarkdown
from ..application.models import Result
from ..core.keyboard import KeyboardBuilder


def command_text(name, request):
    args = [f"/{name}", *request.arguments]
    for flag, value in (
        ("-m", request.mode),
        ("-s", request.steamid),
        ("-q", request.user),
    ):
        if value:
            args.extend((flag, str(value)))
    if request.update:
        args.append("-u")
    if request.overall is not None:
        args.append(str(request.overall))
    if request.comment:
        args.append(request.comment)
    return shlex.join(args)


def render(result: Result, user_id: str):
    lines = [f"# {result.title}", result.description]
    for label, value in result.fields:
        lines.extend((f"## {label}", value))
    for label, url in result.links:
        lines.append(f"[{label}]({url})")
    if result.image:
        lines.append(f"![{result.title}]({result.image})")
    message = MessageSegment.markdown(
        MessageMarkdown(content="\n\n".join(x for x in lines if x)[:12000])
    )
    buttons = []
    for index, (label, name, request) in enumerate(result.choices[:10]):
        buttons.append(
            KeyboardBuilder.button(
                id=f"choice_{index}",
                label=label[:40],
                visited_label="查询中",
                style=1,
                action_type=2,
                permission_type=0,
                action_data=command_text(name, request),
                specify_user_ids=[user_id],
                reply=True,
                enter=True,
            )
        )
    if buttons:
        message += KeyboardBuilder.keyboard(
            *(buttons[i : i + 2] for i in range(0, len(buttons), 2))
        )
    return message
