"""Retire this application's obsolete guild commands after global sync."""

import asyncio

from nonebot import logger
from nonebot.adapters.discord import Bot
from nonebot.adapters.discord.exception import RateLimitException
from ..application.catalog import COMMANDS, BY_NAME


async def remove_stale_guild_commands(bot: Bot) -> int:
    if "*" not in bot.bot_info.application_commands.get("*", []):
        return 0  # Explicit test-guild registration must stay guild-scoped.
    expected = {spec.name for spec in COMMANDS}
    for attempt in range(3):
        registered = await bot.get_global_application_commands(
            application_id=bot.application_id
        )
        if expected.issubset({command.name for command in registered}):
            break
        if attempt == 2:
            logger.warning("Global command sync incomplete; guild cleanup skipped")
            return 0
        await asyncio.sleep(3)
    # Only remove known legacy chat commands owned by this application.
    retired = set(BY_NAME) | {"update_map"}
    removed = 0
    guilds = await bot.get_current_user_guilds(limit=200)
    for guild in guilds:
        commands = await bot.get_guild_application_commands(
            application_id=bot.application_id, guild_id=guild.id
        )
        for command in commands:
            if command.name in retired and command.type == 1:
                for attempt in range(3):
                    try:
                        await bot.delete_guild_application_command(
                            application_id=bot.application_id,
                            guild_id=guild.id,
                            command_id=command.id,
                        )
                        break
                    except RateLimitException:
                        if attempt == 2:
                            raise
                        await asyncio.sleep(5)
                removed += 1
    logger.info(f"Removed {removed} obsolete Discord guild command registrations")
    return removed
