import asyncio
import hashlib
import hmac
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
TEMP = tempfile.TemporaryDirectory()
os.environ["BOT_DATABASE_PATH"] = str(Path(TEMP.name) / "bot.sqlite3")
import nonebot

nonebot.init(_env_file=None, driver="~httpx+~websockets", log_level="WARNING")
assert nonebot.load_plugin("src.plugins.gokz")
assert any(p.name == "unified" for p in nonebot.get_loaded_plugins())

from src.plugins.gokz.application import service
from src.plugins.gokz.application.catalog import BY_NAME, COMMANDS
from src.plugins.gokz.application.commands import (
    definition,
    request_from_result,
    discord_request,
)
from src.plugins.gokz.application.context import RequestContext
from src.plugins.gokz.application.models import CommandInput, Result, UserError
from src.plugins.gokz.presentation import discord, qq
from src.plugins.gokz.plugins.unified import context
from nonebot.adapters.discord.commands.storage import _application_command_storage
from nonebot.adapters.discord.api import MessageFlag


class ApplicationTests(unittest.IsolatedAsyncioTestCase):
    def request(self, name, raw):
        parsed = definition(BY_NAME[name]).parse(raw)
        self.assertTrue(parsed.matched, str(parsed.error_info))
        return request_from_result(parsed, name)

    def test_slash_options_are_lossless(self):
        options = [
            SimpleNamespace(name=k, value=v)
            for k, v in {
                "map": "cakewalk",
                "mode": "VNL",
                "user": "123",
                "comment": "great map -m is part of this comment",
            }.items()
        ]
        request = discord_request(BY_NAME["comment"], options)
        self.assertEqual(request.arguments, ("cakewalk",))
        self.assertEqual(request.comment, "great map -m is part of this comment")
        self.assertEqual(request.mode, "VNL")
        self.assertEqual(request.user, "123")
        rated = discord_request(
            BY_NAME["rate"],
            [
                SimpleNamespace(name=k, value=v)
                for k, v in {
                    "map": "cakewalk",
                    "overall": 5,
                    "comment": '-m "literal comment"',
                }.items()
            ],
        )
        self.assertEqual(rated.arguments, ("cakewalk",))
        self.assertEqual(rated.overall, 5)
        self.assertEqual(rated.comment, '-m "literal comment"')

        self.assertEqual(self.request("pb", "/pb cakewalk skz -u").mode, "skz")
        self.assertTrue(self.request("pb", "/pb cakewalk skz -u").update)

    def test_all_slash_commands_have_english_metadata(self):
        self.assertEqual(len(_application_command_storage), len(COMMANDS))
        for spec in COMMANDS:
            config = _application_command_storage[spec.name]
            self.assertEqual(config.description, spec.en)
            self.assertTrue(config.description.isascii())
        self.assertEqual(_application_command_storage["bind"].options[0].name, "code")

    async def test_shared_code_binds_both_platforms_independently(self):
        secret = "integration-test-secret"
        raw = (12345).to_bytes(4, "big") + (2000000000).to_bytes(4, "big")
        raw += hmac.new(secret.encode(), raw, hashlib.sha256).digest()[:8]
        number = int.from_bytes(raw, "big")
        encoded = ""
        alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        while number:
            number, n = divmod(number, 62)
            encoded = alphabet[n] + encoded
        code = "KZTOP" + encoded.zfill(22)
        qqctx = RequestContext("qq", "same-id")
        dcctx = RequestContext("discord", "same-id")
        with (
            patch.object(service, "QQ_BOT_SECRET", secret),
            patch.object(
                service, "read", AsyncMock(return_value={"name": "Test Player"})
            ),
        ):
            for ctx in (qqctx, dcctx):
                result = await service.execute(
                    ctx, "bind", CommandInput(arguments=(code,))
                )
                self.assertTrue(result.private)
                self.assertEqual(await service.binding(ctx), "76561197960278073")
            service.preference(qqctx, "SKZ")
            service.preference(dcctx, "VNL")
            self.assertEqual(service.preference(qqctx), "SKZ")
            self.assertEqual(service.preference(dcctx), "VNL")
            with self.assertRaises(UserError):
                await service.execute(
                    dcctx, "bind", CommandInput(arguments=("KZTOPinvalid",))
                )
        # Discord cannot change which QQ user owns this Steam account.
        self.assertEqual(await service.binding(qqctx), await service.binding(dcctx))

    async def test_pb_uses_same_feature_for_both_platforms(self):
        request = CommandInput(
            arguments=("bkz_cakewalk",), steamid="76561197960278073", mode="KZT"
        )
        record = {
            "time": 61.25,
            "teleports": 2,
            "map_tier": 1,
            "player_name": "A Player",
        }
        with (
            patch.object(service, "get_maps", AsyncMock()),
            patch.object(
                service,
                "read",
                AsyncMock(return_value=[{"id": 1, "name": "bkz_cakewalk"}]),
            ),
            patch.object(
                service, "fetch_personal_best", AsyncMock(return_value=record)
            ) as fetch,
        ):
            for ctx in (RequestContext("qq", "a"), RequestContext("discord", "b")):
                result = await service.execute(ctx, "pb", request)
                self.assertIn("1:01.250", result.fields[0][1])
                self.assertEqual(result.title, "bkz_cakewalk")
            self.assertEqual(fetch.await_count, 4)

    async def test_help_is_english_and_controls_are_author_bound(self):
        result = await service.execute(
            RequestContext("discord", "123"), "help", CommandInput()
        )
        self.assertFalse(any("\u4e00" <= c <= "\u9fff" for c in result.description))
        result.choices = [("KZT", "mode", CommandInput(arguments=("KZT",)))]
        rendered = discord.render(result, "123")
        token = next(reversed(discord.choices))
        self.assertIsNone(discord.resolve_choice("gokz:" + token, "456"))
        self.assertEqual(discord.resolve_choice("gokz:" + token, "123")[0], "mode")
        with patch.object(discord.time, "monotonic", return_value=10**20):
            self.assertIsNone(discord.resolve_choice("gokz:" + token, "123"))
        self.assertIn("embeds", rendered)

    async def test_private_ack_and_public_result(self):
        bot = SimpleNamespace(
            create_interaction_response=AsyncMock(),
            create_followup_message=AsyncMock(),
            delete_origin_interaction_response=AsyncMock(),
            edit_origin_interaction_response=AsyncMock(),
        )
        event = SimpleNamespace(
            id="1", token="token", application_id="2", get_user_id=lambda: "123"
        )
        await discord.defer(bot, event)
        ack = bot.create_interaction_response.call_args.kwargs["response"]
        self.assertEqual(ack.data.flags, MessageFlag.EPHEMERAL)
        await discord.deliver(bot, event, Result("Records", "Public result"))
        bot.create_followup_message.assert_awaited_once()
        bot.delete_origin_interaction_response.assert_awaited_once()
        await discord.deliver(
            bot, event, Result("Binding", "Private result", private=True)
        )
        bot.edit_origin_interaction_response.assert_awaited_once()

    async def test_discord_event_routes_through_nonebot(self):
        from nonebot.adapters.discord import Adapter, Bot
        from nonebot.adapters.discord.config import BotInfo
        from nonebot.adapters.discord.event import ApplicationCommandInteractionEvent
        from nonebot.message import handle_event

        try:
            adapter = nonebot.get_adapter(Adapter)
        except (KeyError, ValueError):
            nonebot.get_driver().register_adapter(Adapter)
            adapter = nonebot.get_adapter(Adapter)
        event = ApplicationCommandInteractionEvent.model_validate(
            {
                "id": "100",
                "application_id": "1450135161294422291",
                "type": 2,
                "data": {"id": "101", "name": "help", "type": 1},
                "channel_id": "102",
                "user": {
                    "id": "103",
                    "username": "tester",
                    "discriminator": "0",
                    "avatar": None,
                },
                "token": "fake",
                "version": 1,
                "locale": "en-US",
                "app_permissions": "0",
                "entitlements": [],
                "authorizing_integration_owners": {},
                "context": 1,
                "attachment_size_limit": 10485760,
            }
        )
        bot = Bot(adapter, "1450135161294422291", BotInfo(token="fake"))
        with (
            patch.object(
                Bot, "create_interaction_response", AsyncMock(), create=True
            ) as ack,
            patch.object(
                Bot, "create_followup_message", AsyncMock(), create=True
            ) as send,
            patch.object(
                Bot, "delete_origin_interaction_response", AsyncMock(), create=True
            ),
        ):
            await handle_event(bot, event)
            ack.assert_awaited_once()
            send.assert_awaited_once()

    async def test_qq_event_routes_through_nonebot(self):
        from nonebot.adapters.qq import Adapter, Bot
        from nonebot.adapters.qq.config import BotInfo
        from nonebot.adapters.qq.event import C2CMessageCreateEvent
        from nonebot.message import handle_event

        try:
            adapter = nonebot.get_adapter(Adapter)
        except (KeyError, ValueError):
            nonebot.get_driver().register_adapter(Adapter)
            adapter = nonebot.get_adapter(Adapter)
        event = C2CMessageCreateEvent.model_validate(
            {
                "id": "q100",
                "content": "/help",
                "timestamp": "2026-10-30T10:00:00Z",
                "author": {"id": "qq-user", "user_openid": "qq-user"},
            }
        )
        bot = Bot(adapter, "123", BotInfo(id="123", token="fake", secret="fake"))
        with patch.object(Bot, "send", AsyncMock()) as send:
            await handle_event(bot, event)
            send.assert_awaited_once()
            self.assertIn("GOKZ", str(send.call_args.args[1]))

    def test_renderer_limits_and_qq_commands(self):
        result = Result("x" * 400, "x" * 5000, fields=[("y" * 300, "z" * 2000)] * 40)
        payload = discord.render(result, "123")
        embed = payload["embeds"][0]
        self.assertLessEqual(len(embed.fields), 25)
        self.assertLessEqual(
            len(embed.title)
            + len(embed.description)
            + sum(len(f.name) + len(f.value) for f in embed.fields),
            6000,
        )
        self.assertIn(
            "-m VNL",
            qq.command_text("pb", CommandInput(arguments=("cakewalk",), mode="VNL")),
        )

    async def test_admin_commands_restricted(self):
        with self.assertRaises(UserError):
            await service.execute(
                RequestContext("discord", "a"),
                "set_server",
                CommandInput(arguments=("axekz",)),
            )


if __name__ == "__main__":
    unittest.main()
