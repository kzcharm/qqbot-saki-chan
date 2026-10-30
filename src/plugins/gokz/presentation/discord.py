"""English embeds and short-lived, author-bound Discord controls."""

import secrets
import time
from datetime import datetime, timezone
from urllib.parse import quote
from nonebot.adapters.discord.api import EmbedFooter

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


def timestamp(value: str | None, *, fallback: str = "Unknown") -> str:
    if not value:
        return fallback
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return f"<t:{int(dt.timestamp())}:f>"
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
            ("Date", timestamp(record.get("created_at") or record.get("created_on"))),
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
