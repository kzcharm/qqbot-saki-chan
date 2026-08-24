"""Formatting helpers for GOKZ.TOP player profiles."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable
from urllib.parse import quote

from babel import Locale


GOKZ_TOP_PROFILE_BASE_URL = "https://gokz.top/profile"
STEAM_PROFILE_BASE_URL = "https://steamcommunity.com/profiles"
CHINESE_LOCALE = Locale.parse("zh_Hans")


def _markdown_text(value: object) -> str:
    """Escape the few Markdown characters that could alter a player name."""
    return str(value).replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _bilibili_url(social_links: Iterable[dict[str, Any]]) -> str | None:
    for link in social_links:
        if str(link.get("platform", "")).casefold() != "bilibili":
            continue
        url = link.get("url")
        if isinstance(url, str) and url:
            return url
    return None


def country_name_zh(country_code: object) -> str:
    """Return the Chinese display name for an ISO 3166-1 country code."""
    code = str(country_code).upper()
    return CHINESE_LOCALE.territories.get(code, code)


def _date(value: object) -> str:
    if not isinstance(value, str):
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return value


def _hours(stats: dict[str, Any] | None) -> str | None:
    seconds = stats and stats.get("playtime", {}).get("total_seconds")
    if not isinstance(seconds, (int, float)):
        return None
    return f"{seconds / 3600:,.1f} 小时"


def _long_jump(jumpstats: dict[str, Any] | None) -> str | None:
    records = jumpstats.get("data") if isinstance(jumpstats, dict) else None
    distance = records[0].get("distance") if isinstance(records, list) and records else None
    return f"{distance:.2f} units" if isinstance(distance, (int, float)) else None


def _achievement_label(achievement: dict[str, Any]) -> str | None:
    tournament = achievement.get("tournament")
    name = tournament.get("name") if isinstance(tournament, dict) else None
    placement = achievement.get("placement")
    if not isinstance(name, str) or not name:
        return None
    placement_label = {1: "冠军", 2: "亚军", 3: "季军", 4: "四强"}.get(placement)
    return f"{name} {placement_label or f'第 {placement} 名' if isinstance(placement, int) else ''}".strip()


def profile_markdown(
    player: dict[str, Any],
    social_links: Iterable[dict[str, Any]] = (),
    *,
    stats: dict[str, Any] | None = None,
    jumpstats: dict[str, Any] | None = None,
    achievements: dict[str, Any] | None = None,
    leaderboard: dict[str, Any] | None = None,
) -> str:
    """Build the QQ Markdown content for a public GOKZ.TOP player profile."""
    steamid64 = str(player["steamid64"])
    display_name = player.get("alias") or player.get("name") or steamid64
    profile_identifier = str(player.get("custom_id") or steamid64)
    profile_url = f"{GOKZ_TOP_PROFILE_BASE_URL}/{quote(profile_identifier, safe='_-')}/records"
    steam_url = f"{STEAM_PROFILE_BASE_URL}/{quote(steamid64, safe='')}"

    lines = [
        "# 玩家资料",
        f"## {_markdown_text(display_name)}",
        f"- SteamID64: `{steamid64}`",
    ]
    if player.get("country"):
        lines.append(f"- 国家/地区: {country_name_zh(player['country'])}")
    primary_scope = player.get("primary_scope") or player.get("primary_mode")
    if primary_scope:
        lines.append(f"- 主模式: `{primary_scope}`")
    rank_data = leaderboard if isinstance(leaderboard, dict) else {}
    rank = player.get("rank") if player.get("rank") is not None else rank_data.get("rank")
    rating = player.get("rating") if player.get("rating") is not None else rank_data.get("rating")
    points = player.get("points") if player.get("points") is not None else rank_data.get("points")
    if rank is not None:
        lines.append(f"- 全球排名: `#{rank}`")
    regional_rank = rank_data.get("rank_regional") or rank_data.get("regional_rank")
    region = rank_data.get("region")
    if regional_rank is not None and region:
        lines.append(f"- 地区排名: `{region} #{regional_rank}`")
    if rating is not None:
        rating_display = f"{rating:.2f}" if isinstance(rating, (int, float)) else str(rating)
        lines.append(f"- Rating: `{rating_display}`")
    if points is not None:
        lines.append(f"- 积分: `{points:,}`" if isinstance(points, int) else f"- 积分: `{points}`")
    if joined := _date(player.get("created_at")):
        lines.append(f"- 加入时间: `{joined}`")
    if last_played := _date(player.get("last_played_at")):
        lines.append(f"- 最近游玩: `{last_played}`")
    if playtime := _hours(stats):
        lines.append(f"- 游玩时长: `{playtime}`")
    if long_jump := _long_jump(jumpstats):
        lines.append(f"- Long Jump: `{long_jump}`")
    favorite_server = player.get("favorite_server")
    if isinstance(favorite_server, dict) and favorite_server.get("label"):
        group = favorite_server.get("server_group")
        custom_id = group.get("custom_id") if isinstance(group, dict) else None
        if custom_id:
            server_url = f"https://gokz.top/servers/group/{quote(str(custom_id), safe='_-')}"
            lines.append(f"- 最爱服务器: [{_markdown_text(favorite_server['label'])}]({server_url})")
        else:
            lines.append(f"- 最爱服务器: {_markdown_text(favorite_server['label'])}")
    achievement_data = achievements.get("data") if isinstance(achievements, dict) else []
    achievement_labels = [label for item in achievement_data if isinstance(item, dict) if (label := _achievement_label(item))]
    if achievement_labels:
        lines.append(f"- 勋章: {' · '.join(achievement_labels)}")

    links = [f"[GOKZ.TOP]({profile_url})", f"[Steam]({steam_url})"]
    bilibili_url = _bilibili_url(social_links)
    if bilibili_url:
        links.append(f"[Bilibili]({bilibili_url})")
    lines.extend(("", " | ".join(links)))
    return "\n".join(lines)
