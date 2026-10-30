"""English embeds and short-lived, author-bound Discord controls."""

import secrets
import time
from datetime import datetime, timezone
from urllib.parse import quote
from nonebot.adapters.discord.api import EmbedFooter, EmbedAuthor, EmbedThumbnail

from nonebot.adapters.discord import Message, MessageSegment
from nonebot.adapters.discord.api import (
    AllowedMention,
    Button,
    ButtonStyle,
    Embed,
    EmbedField,
    EmbedImage,
    InteractionResponse,
    InteractionCallbackMessage,
    InteractionCallbackType,
    MessageFlag,
)
from nonebot.adapters.discord.message import parse_message
from ..application.models import Result

# Process-local controls expire on restart and after ten minutes.
choices = {}


def render(result: Result, user_id: str):
    now = time.monotonic()
    for key, value in list(choices.items()):
        if value[0] < now:
            choices.pop(key, None)
    image_options = {"image": EmbedImage(url=result.image)} if result.image else {}
    description = result.description[:3000]
    budget = max(100, 5500 - len(description) - len(result.title[:256]))
    per_field = min(1024, max(1, budget // max(1, len(result.fields[:25])) - 100))
    message = Message(
        MessageSegment.embed(
            Embed(
                title=result.title[:256],
                description=description,
                color={"success": 0x2ECC71, "error": 0xE74C3C, "warning": 0xF1C40F}.get(
                    result.tone, 0x6478F0
                ),
                fields=[
                    EmbedField(
                        name=k[:100],
                        value=(v or "—")[:per_field],
                        inline=len(v) < 70 and "\n" not in v,
                    )
                    for k, v in result.fields[:25]
                ],
                **image_options,
            )
        )
    )
    # Specialized Discord layouts retain the shared domain data.
    embed = message[0].data["embed"]
    if result.footer:
        embed.footer = EmbedFooter(text=result.footer)
    if result.category == "records":
        style_records(embed, result)
    elif result.category == "bans":
        style_bans(embed, result)
    elif result.category in {"profile", "rank"}:
        style_player(embed, result)
    elif result.category in {"servers", "server_groups"}:
        style_servers(embed, result)
    if result.file and not result.image:
        embed.image = EmbedImage(url=f"attachment://{result.file.name}")
    # Keep below Discord's 6,000-character embed budget and five component rows.
    for label, url in result.links[:5]:
        message += MessageSegment.component(
            Button(style=ButtonStyle.Link, label=label[:80], url=url)
        )
    for label, name, request in result.choices[: 20 - len(result.links[:5])]:
        if len(choices) >= 2000:
            choices.pop(next(iter(choices)))
        token = secrets.token_urlsafe(18)
        choices[token] = (now + 600, user_id, name, request)
        message += MessageSegment.component(
            Button(
                style=ButtonStyle.Primary, label=label[:80], custom_id=f"gokz:{token}"
            )
        )
    if result.file:
        message += MessageSegment.attachment(
            file=result.file.name, content=result.file.read_bytes()
        )
    return parse_message(message)


def resolve_choice(custom_id, user_id):
    entry = choices.get(custom_id.removeprefix("gokz:"))
    if not entry or entry[0] < time.monotonic() or entry[1] != user_id:
        return None
    return entry[2:]


async def defer(bot, event, *, private: bool = False):
    await bot.create_interaction_response(
        interaction_id=event.id,
        interaction_token=event.token,
        response=InteractionResponse(
            type=InteractionCallbackType.DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE,
            data=InteractionCallbackMessage(
                flags=MessageFlag.EPHEMERAL if private else MessageFlag(0)
            ),
        ),
    )


async def deliver(bot, event, result):
    payload = render(result, event.get_user_id())
    payload["allowed_mentions"] = AllowedMention(
        parse=[], roles=[], users=[], replied_user=False
    )
    # Edit the deferred original in place: one result, no followup or deletion.
    await bot.edit_origin_interaction_response(
        application_id=event.application_id,
        interaction_token=event.token,
        **payload,
    )


def timestamp(
    value: str | None, *, fallback: str = "Unknown", relative: bool = False
) -> str:
    if not value:
        return fallback
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return f"<t:{int(dt.timestamp())}:{'R' if relative else 'f'}>"
    except (ValueError, TypeError):
        return fallback


def style_records(embed: Embed, result: Result) -> None:
    if not result.entries:
        return
    fields = []
    for record in result.entries[:2]:
        kind = record.get("kind", "Record")
        seconds = float(record["time"])
        minutes, secs = divmod(seconds, 60)
        fields.append(
            EmbedField(
                name=f"{kind} Record",
                value=f"**{int(minutes)}:{secs:06.3f}**",
                inline=False,
            )
        )
        player = record.get("player") or {}
        name = (
            player.get("display_name") or record.get("player_name") or "Unknown player"
        )
        steamid = player.get("steamid64") or record.get("steam_id")
        display = (
            f"[{name}](https://steamcommunity.com/profiles/{steamid})"
            if steamid
            else name
        )
        for label, value in (
            ("Player", display),
            ("Mode", str(record.get("mode") or "—").upper()),
            ("Teleports", str(record.get("teleports", 0))),
            ("Rating", str(record.get("rating", record.get("points", "—")))),
            ("Server", str(record.get("server_name") or "Unknown")),
            (
                "Date",
                timestamp(
                    record.get("created_at") or record.get("created_on"),
                    relative=kind == "PR",
                ),
            ),
        ):
            fields.append(EmbedField(name=label, value=value[:500], inline=True))
    embed.fields = fields
    tier = next(
        (r.get("map_tier") for r in result.entries if r.get("map_tier") is not None),
        None,
    )
    link = (
        result.links[0][1]
        if result.links
        else f"https://gokz.top/maps/{quote(result.title, safe='')}/maptop"
    )
    embed.description = f"[**{result.title}**]({link})" + (
        f" · **T{tier}**" if tier is not None else ""
    )


def style_bans(embed: Embed, result: Result) -> None:
    if not result.entries:
        return
    fields = []
    active = False
    for ban in result.entries[:5]:
        expires = ban.get("expires_at") or ban.get("expires_on")
        status = str(ban.get("status") or "")
        if not status:
            if not expires:
                status = "permanent"
            else:
                try:
                    dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    status = "expired" if dt <= datetime.now(timezone.utc) else "active"
                except (ValueError, TypeError):
                    status = "unknown"
        active = active or status in {"active", "permanent"}
        server = ban.get("server") or {}
        server_name = (
            server.get("name")
            or server.get("hostname")
            or (
                f"Server {ban['server_id']}"
                if ban.get("server_id")
                else "Unknown server"
            )
        )
        fields.append(
            EmbedField(
                name=f"{str(ban.get('ban_type', 'other')).replace('_', ' ').title()} · {status.title()}",
                value=(
                    f"**Server:** {server_name}\n**Created:** {timestamp(ban.get('created_at') or ban.get('created_on'))}\n**Expires:** {timestamp(expires, fallback='Never' if status == 'permanent' else '—')}\n**Notes:** {ban.get('notes') or ban.get('reason') or 'No notes provided.'}"
                )[:1000],
                inline=False,
            )
        )
    player = result.entries[0].get("player") or {}
    if player.get("display_name"):
        embed.description = f"**{player['display_name']}**"
    embed.fields = fields
    embed.color = 0xE74C3C if active else 0xF1C40F


def metric(value, *, decimal: bool = False) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):,.2f}" if decimal else f"{int(value):,}"
    except (ValueError, TypeError):
        return "—"


def style_player(embed: Embed, result: Result) -> None:
    if not result.entries:
        return
    data = result.entries[0]
    player = data.get("player") or {}
    rank = data.get("rank") or {}
    steamid = player.get("steamid64")
    name = str(
        player.get("alias")
        or player.get("name")
        or player.get("display_name")
        or steamid
        or "Player"
    )
    scope = data.get("scope", "OVR")
    avatar = player.get("avatar_hash")
    avatar_options = {}
    if (
        isinstance(avatar, str)
        and len(avatar) == 40
        and all(c in "0123456789abcdefABCDEF" for c in avatar)
    ):
        url = f"https://avatars.steamstatic.com/{avatar}_full.jpg"
        avatar_options["icon_url"] = url
        embed.thumbnail = EmbedThumbnail(url=url)
    author_options = (
        {"url": f"https://steamcommunity.com/profiles/{steamid}"} if steamid else {}
    )
    embed.author = EmbedAuthor(name=name[:256], **author_options, **avatar_options)
    embed.title = (
        "Player Profile" if result.category == "profile" else "Player Rankings"
    )
    if steamid:
        embed.url = f"https://gokz.top/profile/{steamid}"
    position = rank.get("rank")
    position_text = f"**#{metric(position)}**" if position else "**Unranked**"
    country = player.get("country") or rank.get("region") or ""
    embed.description = f"**{scope}** · {position_text}" + (
        f" · {country}" if country else ""
    )
    values = [
        ("Rating", f"**{metric(rank.get('rating'), decimal=True)}**"),
        ("Easy rating", metric(rank.get("rating_easy"), decimal=True)),
        ("Hard rating", metric(rank.get("rating_hard"), decimal=True)),
        (
            "Regional rank",
            f"#{metric(rank['rank_regional'])}"
            if rank.get("rank_regional")
            else "Unranked",
        ),
        ("Points", metric(rank.get("points"))),
        ("Maps finished", metric(rank.get("unique_map_finishes"))),
        ("NUB world records", metric(rank.get("wrs_nub"))),
        ("PRO world records", metric(rank.get("wrs_pro"))),
        ("900+ records", metric(rank.get("records_900_plus"))),
    ]
    if result.category == "profile":
        seconds = (
            ((data.get("stats") or {}).get("most_played_server") or {}).get("all_time")
            or {}
        ).get("total_seconds")
        if isinstance(seconds, (float, int)):
            values.append(("Playtime", f"{seconds / 3600:,.1f} hours"))
        values.append(
            (
                "Last played",
                timestamp(
                    player.get("last_played_at") or player.get("last_played"),
                    relative=True,
                ),
            )
        )
        favorite = player.get("favorite_server") or {}
        label = favorite.get("name") or favorite.get("label")
        if label:
            values.append(("Favourite server", str(label)))
    embed.fields = [EmbedField(name=k, value=v[:350], inline=True) for k, v in values]


def style_servers(embed: Embed, result: Result) -> None:
    if result.category == "server_groups":
        embed.title = "Server Groups"
        embed.description = (
            "Choose a group below to view its live servers."
            if result.entries
            else "No servers are currently online."
        )
        embed.fields = [
            EmbedField(
                name=str(group["name"])[:100],
                value=f"`{group['slug']}` · **{group['servers']}** servers · **{group['players']}** players",
                inline=True,
            )
            for group in result.entries[:20]
        ]
        embed.footer = EmbedFooter(text=f"{len(result.entries)} online groups")
        return
    if not result.entries:
        return
    embed.color = 0x2ECC71
    players = sum(
        int((row.get("live_status") or {}).get("player_count") or 0)
        for row in result.entries
    )
    embed.description = (
        f"**{len(result.entries)}** online servers · **{players}** players"
    )
    fields = []
    for row in result.entries[:8]:
        live = row.get("live_status") or {}
        map_name = str(live.get("map") or "Unknown map")
        map_url = f"https://gokz.top/maps/{quote(map_name, safe='')}/maptop"
        tier = f" · **T{row['map_tier']}**" if row.get("map_tier") is not None else ""
        count = f"{live.get('player_count', 0)}/{live.get('max_players', 0)}"
        roster = " · ".join(
            str(p.get("name", "")).replace("`", "")[:24]
            for p in (live.get("players") or [])[:8]
        )
        address = f"{row.get('ip', '')}:{row.get('port', '')}"
        value = f"**Map:** [{map_name}]({map_url}){tier}\n**Players:** {count} · **Region:** {row.get('region') or '—'}"
        if roster:
            value += f"\n`{roster}`"
        if row.get("ip") and row.get("port"):
            value += f"\n```\nconnect {address}\n```"
        fields.append(
            EmbedField(
                name=str(live.get("hostname") or address)[:100],
                value=value[:500],
                inline=False,
            )
        )
    embed.fields = fields
    embed.footer = EmbedFooter(
        text=f"Showing {len(fields)} of {len(result.entries)} online servers · full list via Server group"
    )
