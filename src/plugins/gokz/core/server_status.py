from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any, Optional
from urllib.parse import quote


SERVER_GROUP_PAGE_URL = "https://gokz.top/servers/group/{group_slug}"


def _markdown_text(value: object) -> str:
    text = str(value or "未知")
    return text.replace("\\", "\\\\").replace("`", "\\`").replace("*", "\\*").replace("\n", " ")


def player_label(player: Mapping[str, object]) -> str:
    """Render a live player with their clan tag only."""
    tag = str(player.get("tag") or player.get("mode") or "").strip()
    name = _markdown_text(player.get("name"))
    display_name = f"{tag} {name}".strip()
    return f"`{display_name}`"


def player_name(player: Mapping[str, object]) -> str:
    """Render a live player name without their clan tag."""
    return f"`{_markdown_text(player.get('name'))}`"


def _servers_by_group(servers: Iterable[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for server in servers:
        group = server.get("group")
        if not isinstance(group, Mapping):
            continue
        slug = group.get("custom_id")
        if isinstance(slug, str) and slug:
            groups[slug.lower()].append(server)
    return dict(groups)


def _online_servers(servers: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [
        server
        for server in servers
        if isinstance(server.get("live_status"), Mapping)
        and server["live_status"].get("is_online")
    ]


def _region_name(server: Mapping[str, Any]) -> str:
    return str(server.get("region") or "其他地区")


def _server_name(server: Mapping[str, Any]) -> str:
    live = server.get("live_status")
    if isinstance(live, Mapping) and live.get("hostname"):
        return str(live["hostname"])
    return f"{server.get('ip', '未知')}:{server.get('port', '?')}"


def _server_group_page_url(server: Mapping[str, Any]) -> Optional[str]:
    group = server.get("group")
    if not isinstance(group, Mapping) or not group.get("custom_id"):
        return None
    return SERVER_GROUP_PAGE_URL.format(group_slug=quote(str(group["custom_id"]), safe="_-"))


def _region_sort_key(region: str) -> tuple[int, str]:
    return (0, "") if region.upper() == "CN" else (1, region)


def _group_sort_key(item: tuple[str, list[Mapping[str, Any]]]) -> tuple[int, str]:
    slug, group_servers = item
    name = str(group_servers[0]["group"].get("name", slug)).lower()
    return (0, name) if slug == "axekz" else (1, name)


def resolve_server_group_slug(
    servers: Iterable[Mapping[str, Any]], identifier: str
) -> Optional[str]:
    """Resolve an exact group ID first, then an unambiguous display name."""
    query = identifier.strip().lower()
    grouped = _servers_by_group(servers)
    if query in grouped:
        return query

    matches = {
        slug
        for slug, group_servers in grouped.items()
        if str(group_servers[0]["group"].get("name") or "").strip().lower() == query
    }
    return matches.pop() if len(matches) == 1 else None


def cn_server_group_choices(servers: Iterable[Mapping[str, Any]]) -> list[tuple[str, str]]:
    """Return online CN groups for the compact quick-access keyboard."""
    groups: dict[str, str] = {}
    for server in _online_servers(servers):
        if _region_name(server).upper() != "CN":
            continue
        group = server.get("group")
        if not isinstance(group, Mapping) or not isinstance(group.get("custom_id"), str):
            continue
        groups[group["custom_id"].lower()] = str(group.get("name") or group["custom_id"])
    return sorted(groups.items(), key=lambda item: (item[0] != "axekz", item[1].lower()))


def server_groups_markdown(servers: Iterable[Mapping[str, Any]]) -> str:
    """Render available server groups from the public live-server response."""
    by_region: dict[str, dict[str, list[Mapping[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for server in _online_servers(servers):
        group = server.get("group")
        if not isinstance(group, Mapping) or not isinstance(group.get("custom_id"), str):
            continue
        by_region[_region_name(server)][group["custom_id"].lower()].append(server)

    if not by_region:
        return "# 服务器组\n\n暂时没有可用的服务器组。"

    lines = ["# 可用服务器组", ""]
    for region, groups in sorted(by_region.items(), key=lambda item: _region_sort_key(item[0])):
        lines.extend((f"## {region}", ""))
        for slug, group_servers in sorted(groups.items(), key=_group_sort_key):
            group = group_servers[0]["group"]
            players = sum(
                int(server["live_status"].get("player_count") or 0)
                for server in group_servers
            )
            lines.append(
                f"- **{_markdown_text(group.get('name'))}** (`{slug}`) · {len(group_servers)} 服务器 · {players} 玩家"
            )
        lines.append("")
    lines.append("")
    lines.append("使用 `/server <组名>` 查看服务器状态，例如 `/server axekz`。")
    return "\n".join(lines)


def server_group_status_markdown(
    servers: Iterable[Mapping[str, Any]], group_slug: str
) -> Optional[str]:
    """Render a server group's current status, or ``None`` when it is unknown."""
    resolved_slug = resolve_server_group_slug(servers, group_slug)
    group_servers = _online_servers(_servers_by_group(servers).get(resolved_slug or "", []))
    if not group_servers:
        return None

    group = group_servers[0]["group"]
    by_region: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for server in group_servers:
        by_region[_region_name(server)].append(server)

    lines = [f"# {_markdown_text(group.get('name'))} 服务器状态", ""]
    for region, region_servers in sorted(by_region.items(), key=lambda item: _region_sort_key(item[0])):
        lines.extend((f"## {region}", ""))
        for server in sorted(region_servers, key=_server_name):
            live = server["live_status"]
            hostname = _markdown_text(_server_name(server))
            map_name = _markdown_text(live.get("map") or "未知地图")
            tier = f" · T{server['map_tier']}" if server.get("map_tier") is not None else ""
            server_name = f"[**{hostname}**]({_server_group_page_url(server)})" if _server_group_page_url(server) else f"**{hostname}**"
            lines.append(f"- {server_name} · *{map_name}*{tier}")
            players = live.get("players")
            if isinstance(players, list) and players:
                player_formatter = player_name if len(players) > 5 else player_label
                player_names = " · ".join(
                    player_formatter(player)
                    for player in players
                    if isinstance(player, Mapping) and player.get("name")
                )
                if player_names:
                    lines.append(f"  {player_names}")
        lines.append("")
    return "\n".join(lines)
