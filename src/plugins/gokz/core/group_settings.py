from __future__ import annotations

from typing import Optional


def group_chat_id(event: object) -> Optional[str]:
    """Return the QQ adapter group ID, with a legacy-compatible fallback."""
    group_id = getattr(event, "group_openid", None) or getattr(event, "group_id", None)
    return str(group_id) if group_id else None


def group_info_markdown(group_id: str, server_group: Optional[str]) -> str:
    """Render basic information for the current group chat."""
    default_server = f"`{server_group}`" if server_group else "未设置"
    return "\n".join((
        "# 群组信息",
        "",
        f"- 群组 ID: `{group_id}`",
        f"- 默认服务器组: {default_server}",
    ))


def set_server_target(
    arguments: tuple[str, ...], current_group_id: Optional[str]
) -> Optional[tuple[str, str]]:
    """Resolve ``/set_server`` arguments to a target group and server group.

    A single argument targets the current group. Two or more arguments use
    the first as an explicit group ID, which lets root users configure a
    group without joining it.
    """
    if not arguments:
        return None
    if len(arguments) == 1:
        if not current_group_id:
            return None
        return current_group_id, arguments[0]
    return arguments[0], " ".join(arguments[1:])
