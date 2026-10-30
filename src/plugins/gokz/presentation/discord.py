"""English embeds and short-lived, author-bound Discord controls."""

import secrets
import time

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
                color=0x6478F0,
                fields=[
                    EmbedField(name=k[:100], value=(v or "—")[:per_field], inline=False)
                    for k, v in result.fields[:25]
                ],
                **image_options,
            )
        )
    )
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


async def defer(bot, event):
    await bot.create_interaction_response(
        interaction_id=event.id,
        interaction_token=event.token,
        response=InteractionResponse(
            type=InteractionCallbackType.DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE,
            data=InteractionCallbackMessage(flags=MessageFlag.EPHEMERAL),
        ),
    )


async def deliver(bot, event, result):
    payload = render(result, event.get_user_id())
    payload["allowed_mentions"] = AllowedMention(
        parse=[], roles=[], users=[], replied_user=False
    )
    if result.private:
        await bot.edit_origin_interaction_response(
            application_id=event.application_id,
            interaction_token=event.token,
            **payload,
        )
    else:
        # Completing the private deferred response first prevents Discord from
        # treating the first followup as an edit of @original. Deleting
        # @original after that alias would delete the result the user just saw.
        await bot.edit_origin_interaction_response(
            application_id=event.application_id,
            interaction_token=event.token,
            content="Your result is ready below.",
            allowed_mentions=payload["allowed_mentions"],
        )
        await bot.create_followup_message(
            application_id=event.application_id,
            interaction_token=event.token,
            flags=MessageFlag(0),
            **payload,
        )
