"""QQ input and legacy interactions around the shared feature executor.

This module owns transport compatibility, never API queries or feature writes.
"""

from typing import Any

from nonebot import get_driver

from ..application import service
from ..application.context import RequestContext
from ..application.models import CommandInput, Result, UserError
from ..core.binding_message import binding_help_message
from ..core.map_selection import map_command, map_selection_message


def context(event: Any) -> RequestContext:
    account = event.get_user_id()
    roots = get_driver().config.superusers
    return RequestContext(
        "qq",
        account,
        getattr(event, "group_openid", None) or getattr(event, "group_id", None),
        frozenset({"root"})
        if account in roots or f"qq:{account}" in roots
        else frozenset(),
    )


def command_input(cd: Any) -> CommandInput:
    return CommandInput(
        arguments=tuple(cd.args),
        mode=cd.mode,
        steamid=cd.steamid,
        update=cd.update,
    )


async def query(
    matcher: Any,
    event: Any,
    name: str,
    request: CommandInput,
    *,
    target: str | None = None,
) -> Result:
    """Execute once, translating only transport-specific errors and choices."""
    try:
        result = await service.execute(context(event), name, request)
    except UserError as exc:
        if exc.en == "Connect your account with /bind first.":
            await matcher.finish(binding_help_message())
        else:
            await matcher.finish(exc.zh)
        raise AssertionError("Matcher.finish must stop execution")
    if result.choices and not result.data:
        if name in {"pb", "wr", "mp"}:
            arguments = ("-m", str(request.mode or "OVR").upper())
            if target:
                arguments += ("-s", target)
        elif name == "comment":
            arguments = (request.comment or "",)
        else:
            arguments = request.arguments[1:]
        await matcher.finish(
            map_selection_message(
                [label for label, _, _ in result.choices],
                lambda selected: map_command(name, selected, *arguments),
                event.get_user_id(),
            )
        )
    return result


# Existing commands retain bespoke legacy views. A new catalog feature without
# a custom view automatically uses QQ's shared Markdown/keyboard renderer.
CUSTOM_VIEWS = frozenset(
    {
        "help",
        "bind",
        "mode",
        "info",
        "profile",
        "api",
        "kz",
        "pb",
        "pr",
        "wr",
        "ban",
        "rank",
        "mp",
        "daily",
        "server",
        "group_info",
        "set_server",
        "find",
        "ccf",
        "review",
        "rate",
        "comment",
        "pw",
        "feedback",
    }
)
