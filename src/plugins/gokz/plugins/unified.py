"""Transport entrypoints for the shared GOKZ application."""

import asyncio
from dataclasses import replace

from healthcheck import HEALTH_PATH
from arclet.alconna import Arparma
from nonebot import get_driver, logger, on_notice
from nonebot.adapters import Bot, Event
from nonebot.adapters.discord import Bot as DiscordBot
from nonebot.adapters.discord.api import (
    StringOption,
    IntegerOption,
    BooleanOption,
    UserOption,
)
from nonebot.adapters.discord.commands.matcher import ApplicationCommandConfig
from nonebot.adapters.discord.commands.storage import _application_command_storage
from nonebot.adapters.discord.api import ApplicationCommandType
from nonebot.adapters.discord.event import (
    ApplicationCommandInteractionEvent,
    MessageComponentInteractionEvent,
)
from nonebot.adapters.qq import Bot as QQBot, MessageSegment
from nonebot_plugin_alconna import on_alconna, UniMessage
from nonebot_plugin_alconna.params import AlconnaMatches
from nonebot_plugin_alconna.builtins.extensions.discord import DiscordSlashExtension

from ..application.catalog import COMMANDS, CommandSpec
from ..application.commands import definition, request_from_result, discord_tokens
from ..application.context import RequestContext
from ..application.models import CommandInput, Result, UserError
from ..application.service import execute
from ..presentation import discord, qq


class GokzSlashExtension(DiscordSlashExtension):
    def __init__(self, spec: CommandSpec) -> None:
        self.spec = spec
        super().__init__(description=spec.en, default_permission=True, nsfw=False)

    def post_init(self, alc):
        self.using = True
        self.application_command = ApplicationCommandConfig(
            type=ApplicationCommandType.CHAT_INPUT,
            name=self.spec.name,
            description=self.spec.en,
            options=[],
            default_permission=True,
            nsfw=False,
        )
        _application_command_storage[self.spec.name] = self.application_command
        options = []
        if self.spec.argument:
            options.append(
                StringOption(
                    name=self.spec.argument,
                    description=self.spec.argument.replace("_", " ").capitalize(),
                    required=False,
                )
            )
        if self.spec.name in {"rate", "comment"}:
            if self.spec.name == "rate":
                options.extend(
                    IntegerOption(
                        name=k,
                        description=f"{k.capitalize()} stars (1–5)",
                        required=False,
                        min_value=1,
                        max_value=5,
                    )
                    for k in ("overall", "gameplay", "visuals")
                )
            options.append(
                StringOption(
                    name="comment",
                    description="Your comment (up to 1,000 characters)",
                    required=False,
                )
            )
        if self.spec.name not in {
            "help",
            "bind",
            "api",
            "server",
            "group_info",
            "set_server",
            "find",
            "feedback",
            "mode",
            "group_rank",
        }:
            options.extend(
                (
                    StringOption(
                        name="mode", description="OVR, KZT, SKZ, or VNL", required=False
                    ),
                    StringOption(
                        name="steamid", description="Look up a Steam ID", required=False
                    ),
                    UserOption(
                        name="user",
                        description="Look up a linked Discord user",
                        required=False,
                    ),
                    BooleanOption(
                        name="update",
                        description="Refresh cached output",
                        required=False,
                    ),
                )
            )
        self.application_command.options = options

    async def message_provider(self, event, state, bot, use_origin=False):
        if not isinstance(event, ApplicationCommandInteractionEvent):
            return None
        return UniMessage(discord_tokens(self.spec, event.data.options))


def context(bot: Bot, event: Event) -> RequestContext:
    platform = "discord" if isinstance(bot, DiscordBot) else "qq"
    account = event.get_user_id()
    if platform == "discord":
        guild = getattr(event, "guild_id", None)
        conversation = str(guild) if guild and str(guild).isdigit() else None
    else:
        conversation = getattr(event, "group_openid", None) or getattr(
            event, "group_id", None
        )
    superusers = get_driver().config.superusers
    root = (
        f"{platform}:{account}" in superusers
        or platform == "qq"
        and account in superusers
    )
    return RequestContext(
        platform,
        account,
        str(conversation) if conversation else None,
        frozenset({"root"}) if root else frozenset(),
    )


async def dispatch(bot: Bot, event: Event, name: str, request: CommandInput) -> None:
    ctx = context(bot, event)
    if ctx.platform == "discord":
        await discord.defer(bot, event)
    else:
        # QQ mentions contain an open ID, never a Steam ID.
        for segment in event.get_message():
            if segment.type == "at":
                request = replace(
                    request, user=segment.data.get("qq") or segment.data.get("id")
                )
                break
    try:
        result = await execute(ctx, name, request)
    except UserError as exc:
        result = Result(
            "Error" if ctx.platform == "discord" else "提示",
            exc.en if ctx.platform == "discord" else exc.zh,
            private=True,
        )
    except Exception:
        logger.exception(f"{ctx.platform} command {name} failed")
        result = Result(
            "Error" if ctx.platform == "discord" else "提示",
            "The service is temporarily unavailable. Please try again."
            if ctx.platform == "discord"
            else "服务暂时不可用，请稍后重试。",
            private=True,
        )
    if ctx.platform == "discord":
        await discord.deliver(bot, event, result)
    else:
        await bot.send(event, qq.render(result, ctx.account_id))
        if result.file:
            await bot.send(event, MessageSegment.file_image(result.file))
        if result.record:
            from ..core.pr_compliment import maybe_send_pr_compliment

            steamid = (
                request.steamid
                or result.record.get("steam_id")
                or (result.record.get("player") or {}).get("steamid64")
            )
            if steamid:
                task = asyncio.create_task(
                    maybe_send_pr_compliment(bot, event, result.record, str(steamid))
                )
                task.add_done_callback(
                    lambda t: t.exception() if not t.cancelled() else None
                )


def register(spec: CommandSpec) -> None:
    matcher = on_alconna(
        definition(spec),
        aliases=set(spec.aliases),
        extensions=[GokzSlashExtension(spec)],
        auto_send_output=False,
        block=True,
        priority=5,
    )

    @matcher.handle()
    async def handle(bot: Bot, event: Event, matches: Arparma = AlconnaMatches()):
        try:
            request = request_from_result(matches, spec.name)
        except UserError as exc:
            ctx = context(bot, event)
            result = Result(
                "Error" if ctx.platform == "discord" else "提示",
                exc.en if ctx.platform == "discord" else exc.zh,
                private=True,
            )
            if ctx.platform == "discord":
                await discord.defer(bot, event)
                await discord.deliver(bot, event, result)
            else:
                await bot.send(event, qq.render(result, ctx.account_id))
            return
        if isinstance(event, ApplicationCommandInteractionEvent):
            values = {
                o.name: o.value
                for o in (
                    event.data.options if isinstance(event.data.options, list) else []
                )
            }
            request = replace(
                request,
                overall=values.get("overall"),
                gameplay=values.get("gameplay"),
                visuals=values.get("visuals"),
                comment=values.get("comment"),
            )
        await dispatch(bot, event, spec.name, request)


for spec in COMMANDS:
    register(spec)


async def is_component(event: Event) -> bool:
    return isinstance(
        event, MessageComponentInteractionEvent
    ) and event.data.custom_id.startswith("gokz:")


component = on_notice(rule=is_component, priority=4, block=True)


@component.handle()
async def handle_component(bot: DiscordBot, event: MessageComponentInteractionEvent):
    choice = discord.resolve_choice(event.data.custom_id, event.get_user_id())
    if choice:
        await dispatch(bot, event, *choice)
    else:
        await discord.defer(bot, event)
        await discord.deliver(
            bot,
            event,
            Result(
                "Control expired",
                "This control expired or belongs to another user. Run the command again.",
                private=True,
            ),
        )


# Health state is recreated for every process and tracks actual adapter events.

HEALTH_PATH.unlink(missing_ok=True)
connected_platforms = {}


@get_driver().on_bot_connect
async def connected(bot: Bot) -> None:
    platform = "discord" if isinstance(bot, DiscordBot) else "qq"
    connected_platforms[bot.self_id] = platform
    HEALTH_PATH.write_text(
        __import__("json").dumps(sorted(set(connected_platforms.values())))
    )
    logger.info(f"{platform} bot connected: {bot.self_id}")


@get_driver().on_bot_disconnect
async def disconnected(bot: Bot) -> None:
    connected_platforms.pop(bot.self_id, None)
    HEALTH_PATH.write_text(
        __import__("json").dumps(sorted(set(connected_platforms.values())))
    )


def register_qq_diagnostic(name: str) -> None:
    matcher = on_alconna(
        "/" + name,
        auto_send_output=False,
        block=True,
        priority=5,
        rule=lambda bot: isinstance(bot, QQBot),
    )

    @matcher.handle()
    async def diagnostic(bot: QQBot, event: Event):
        from nonebot.adapters.qq.models import MessageMarkdown

        content = "# Markdown 测试\n\n**加粗**、_斜体_、~~删除线~~\n\n[打开 GOKZ.TOP](https://gokz.top)\n\n> 测试完成。"
        if name == "test":
            result = Result(
                "图片与键盘测试",
                image="https://api.gokz.top/v1/maps/images/bkz_apricity_v3.webp",
                choices=[("再次测试", "test", CommandInput())],
            )
            await bot.send(event, qq.render(result, event.get_user_id()))
        else:
            await bot.send(
                event, MessageSegment.markdown(MessageMarkdown(content=content))
            )


register_qq_diagnostic("test")
register_qq_diagnostic("markdown_test")
