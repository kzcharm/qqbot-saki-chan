"""Transport entrypoints for the shared GOKZ application."""

from arclet.alconna import Arparma
from healthcheck import HEALTH_PATH
from nonebot import get_driver, logger, on_notice
from nonebot.adapters import Bot, Event
from nonebot.adapters.discord import Bot as DiscordBot
from nonebot.adapters.discord.api import (
    ApplicationCommandType,
    BooleanOption,
    IntegerOption,
    StringOption,
    UserOption,
)
from nonebot.adapters.discord.commands.matcher import ApplicationCommandConfig
from nonebot.adapters.discord.commands.storage import _application_command_storage
from nonebot.adapters.discord.event import (
    ApplicationCommandInteractionEvent,
    MessageComponentInteractionEvent,
)
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import UniMessage, on_alconna
from nonebot_plugin_alconna.builtins.extensions.discord import DiscordSlashExtension
from nonebot_plugin_alconna.params import AlconnaMatches

from ..application import service
from ..application.catalog import COMMANDS, CommandSpec
from ..application.commands import definition, discord_request, request_from_result
from ..application.context import RequestContext
from ..application.models import CommandInput, Result, UserError
from ..presentation import discord, qq
from ..presentation.qq_bridge import CUSTOM_VIEWS


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
        return UniMessage(f"/{self.spec.name}")


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


async def dispatch(
    bot: Bot, event: Event, name: str, request: CommandInput
) -> None:
    ctx = context(bot, event)
    if ctx.platform == "qq":
        try:
            result = await service.execute(ctx, name, request)
        except UserError as exc:
            result = Result("提示", exc.zh, tone=exc.tone)
        await bot.send(event, qq.render(result, ctx.account_id))
        return
    if name not in {
        "help",
        "bind",
        "api",
        "server",
        "group_info",
        "set_server",
        "find",
        "feedback",
        "group_rank",
        "wr",
        "review",
    }:
        try:
            await service.player(ctx, request, own=name in {"rate", "comment", "pk", "mode"})
        except UserError as exc:
            await discord.defer(bot, event, private=True)
            await discord.deliver(
                bot,
                event,
                Result("Account connection", exc.en, private=True, tone=exc.tone),
            )
            return
    await discord.defer(
        bot, event, private=name in {"bind", "set_server", "group_rank"}
    )
    try:
        result = await service.execute(ctx, name, request)
    except UserError as exc:
        result = Result(
            "Error" if exc.tone == "error" else "Warning",
            exc.en,
            private=True,
            tone=exc.tone,
        )
    except Exception:
        logger.exception(f"Discord command {name} failed")
        result = Result(
            "Error",
            "The service is temporarily unavailable. Please try again.",
            private=True,
            tone="error",
        )
    await discord.deliver(bot, event, result)


def register(spec: CommandSpec) -> None:
    matcher = on_alconna(
        definition(spec),
        rule=lambda bot: isinstance(bot, DiscordBot) or (isinstance(bot, QQBot) and spec.name not in CUSTOM_VIEWS),
        aliases=set(spec.aliases),
        extensions=[GokzSlashExtension(spec)],
        auto_send_output=False,
        block=True,
        priority=5 if spec.name in CUSTOM_VIEWS else 0,
    )

    @matcher.handle()
    async def handle(bot: Bot, event: Event, matches: Arparma = AlconnaMatches()):
        try:
            request = request_from_result(matches, spec.name)
        except UserError as exc:
            ctx = context(bot, event)
            result = Result(
                "Warning" if ctx.platform == "discord" else "提示",
                exc.en if ctx.platform == "discord" else exc.zh,
                private=True,
                tone=exc.tone,
            )
            if ctx.platform == "discord":
                await discord.defer(bot, event, private=True)
                await discord.deliver(bot, event, result)
            return
        if isinstance(event, ApplicationCommandInteractionEvent):
            request = discord_request(spec, event.data.options)
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
        await discord.defer(bot, event, private=True)
        await discord.deliver(
            bot,
            event,
            Result(
                "Control expired",
                "This control expired or belongs to another user. Run the command again.",
                private=True,
                tone="warning",
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
    if isinstance(bot, DiscordBot):
        from ..presentation.discord_commands import remove_stale_guild_commands

        try:
            await remove_stale_guild_commands(bot)
        except Exception:
            logger.exception("Unable to clean up obsolete Discord guild commands")


@get_driver().on_bot_disconnect
async def disconnected(bot: Bot) -> None:
    connected_platforms.pop(bot.self_id, None)
    HEALTH_PATH.write_text(
        __import__("json").dumps(sorted(set(connected_platforms.values())))
    )
