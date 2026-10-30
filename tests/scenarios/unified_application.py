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

    async def test_profile_uses_public_social_link_endpoint(self):
        steam = "76561197960278073"

        async def api(path, **kwargs):
            routes = {
                f"/players/{steam}": {"steamid64": steam, "name": "Test Player"},
                f"/player-social-links/players/{steam}": {
                    "data": [
                        {
                            "platform": "youtube",
                            "verified": True,
                            "url": "https://youtube.com/@test",
                        }
                    ]
                },
                f"/players/{steam}/stats": {},
                f"/leaderboards/players/{steam}": {"rank": 3, "rating": 100},
            }
            if path not in routes:
                raise UserError(
                    "GOKZ.TOP is temporarily unavailable. Please try again.", "API错误"
                )
            return routes[path]

        with patch.object(service, "read", side_effect=api):
            result = await service.execute(
                RequestContext("discord", "a"), "profile", CommandInput(steamid=steam)
            )
        self.assertIn(("youtube", "https://youtube.com/@test"), result.links)
        self.assertEqual(result.title, "Test Player")

    async def test_profile_survives_optional_section_failure(self):
        steam = "76561197960278073"

        async def api(path, **kwargs):
            if path == f"/players/{steam}":
                return {"steamid64": steam, "name": "Test Player"}
            raise UserError("Unavailable", "不可用", tone="error")

        with patch.object(service, "read", side_effect=api):
            result = await service.execute(
                RequestContext("discord", "a"), "profile", CommandInput(steamid=steam)
            )
        self.assertEqual(result.title, "Test Player")
        self.assertEqual(result.tone, "warning")
        self.assertEqual(discord.render(result, "a")["embeds"][0].color, 0xF1C40F)

    def test_player_server_layouts_and_relative_pr_dates(self):
        profile = {
            "steamid64": "76561197960278073",
            "name": "Test Player",
            "avatar_hash": "a" * 40,
            "last_played_at": "2026-01-01T00:00:00Z",
        }
        rank = {
            "rank": 12,
            "rating": 1234.56,
            "rating_easy": 1200,
            "rating_hard": 1300,
            "points": 4000,
            "unique_map_finishes": 42,
        }
        result = Result(
            "Test Player",
            category="rank",
            entries=[{"player": profile, "rank": rank, "scope": "OVR"}],
        )
        embed = discord.render(result, "a")["embeds"][0]
        self.assertEqual(embed.author.name, "Test Player")
        self.assertIn("avatars.steamstatic.com", embed.thumbnail.url)
        self.assertIn("#12", embed.description)
        self.assertIn("1,234.56", embed.fields[0].value)
        server = {
            "ip": "127.0.0.1",
            "port": 27015,
            "region": "DE",
            "map_tier": 3,
            "live_status": {
                "hostname": "Test Server",
                "map": "bkz_cakewalk",
                "player_count": 2,
                "max_players": 16,
                "players": [{"name": "Player"}],
            },
        }
        embed = discord.render(
            Result("Servers", category="servers", entries=[server]), "a"
        )["embeds"][0]
        self.assertIn("connect 127.0.0.1:27015", embed.fields[0].value)
        self.assertIn("2/16", embed.fields[0].value)
        record = {"kind": "PR", "time": 60, "created_on": "2026-01-01T00:00:00Z"}
        embed = discord.render(
            Result("Map", category="records", entries=[record]), "a"
        )["embeds"][0]
        self.assertTrue(
            next(f.value for f in embed.fields if f.name == "Date").endswith(":R>")
        )
        self.assertNotEqual(
            discord.render(Result("Warning", tone="warning"), "a")["embeds"][0].color,
            discord.render(Result("Error", tone="error"), "a")["embeds"][0].color,
        )

    async def test_stale_commands_only_removed_after_global_sync(self):
        from src.plugins.gokz.presentation.discord_commands import (
            remove_stale_guild_commands,
        )

        legacy = SimpleNamespace(id="1", name="ban", type=1)
        unrelated = SimpleNamespace(id="2", name="custom", type=1)
        context_menu = SimpleNamespace(id="3", name="ban", type=3)
        bot = SimpleNamespace(
            application_id="app",
            bot_info=SimpleNamespace(application_commands={"*": ["*"]}),
            get_global_application_commands=AsyncMock(
                return_value=[SimpleNamespace(name=s.name) for s in COMMANDS]
            ),
            get_current_user_guilds=AsyncMock(
                return_value=[SimpleNamespace(id="guild")]
            ),
            get_guild_application_commands=AsyncMock(
                return_value=[legacy, unrelated, context_menu]
            ),
            delete_guild_application_command=AsyncMock(),
        )
        self.assertEqual(await remove_stale_guild_commands(bot), 1)
        bot.delete_guild_application_command.assert_awaited_once_with(
            application_id="app", guild_id="guild", command_id="1"
        )
        bot.delete_guild_application_command.reset_mock()
        bot.bot_info.application_commands = {"*": ["test-guild"]}
        self.assertEqual(await remove_stale_guild_commands(bot), 0)
        bot.delete_guild_application_command.assert_not_awaited()

    async def test_status_colours_ban_details_and_record_images(self):
        from src.plugins.gokz.api.global_status import GlobalAPIStatus

        ctx = RequestContext("discord", "123")
        for available, colour in ((True, 0x2ECC71), (False, 0xE74C3C)):
            with patch.object(
                service,
                "check_global_api",
                AsyncMock(return_value=GlobalAPIStatus(available, 123)),
            ):
                result = await service.execute(ctx, "api", CommandInput())
                self.assertEqual(
                    discord.render(result, "123")["embeds"][0].color, colour
                )
        ban = {
            "ban_type": "bhop_hack",
            "notes": "Repeated automated jumps",
            "server_id": 7,
            "created_at": "2026-01-01T00:00:00Z",
            "expires_at": None,
            "player": {"display_name": "Test Player"},
        }
        with (
            patch.object(
                service, "player", AsyncMock(return_value="76561197960278073")
            ),
            patch.object(service, "fetch_personal_bans", AsyncMock(return_value=[ban])),
        ):
            result = await service.execute(ctx, "ban", CommandInput())
        embed = discord.render(result, "123")["embeds"][0]
        self.assertIn("Bhop Hack", embed.fields[0].name)
        self.assertIn("Repeated automated jumps", embed.fields[0].value)
        self.assertIn("Never", embed.fields[0].value)
        self.assertIn("<t:", embed.fields[0].value)
        self.assertEqual(embed.color, 0xE74C3C)
        record = {
            "time": 61.25,
            "teleports": 2,
            "map_tier": 3,
            "map_name": "bkz_cakewalk",
            "mode": "KZT",
            "player_name": "Test Player",
            "created_on": "2026-01-01T00:00:00Z",
        }
        for kind in ("PR", "NUB", "PRO"):
            result = service.record_result(ctx, "bkz_cakewalk", [(kind, record)], "KZT")
            embed = discord.render(result, "123")["embeds"][0]
            self.assertIn("/maps/images/bkz_cakewalk.webp", embed.image.url)
            self.assertTrue(any(f.inline for f in embed.fields))
            self.assertIn("**1:01.250**", embed.fields[0].value)

    async def test_public_result_survives_deferred_response_aliasing(self):
        # Discord treats the first followup after a deferred ACK as an edit
        # of @original, unless the original response was completed explicitly.
        messages = {}
        pending = [False]

        async def acknowledge(**kwargs):
            pending[0] = True
            messages["original"] = {
                "private": bool(kwargs["response"].data.flags & MessageFlag.EPHEMERAL)
            }

        async def edit_original(**payload):
            pending[0] = False
            messages["original"] = {
                "private": messages["original"]["private"],
                **payload,
            }

        async def followup(**payload):
            key = "original" if pending[0] else "followup"
            messages[key] = {"private": pending[0], **payload}
            pending[0] = False

        async def delete_original(**kwargs):
            messages.pop("original", None)

        bot = SimpleNamespace(
            create_interaction_response=AsyncMock(side_effect=acknowledge),
            edit_origin_interaction_response=AsyncMock(side_effect=edit_original),
            create_followup_message=AsyncMock(side_effect=followup),
            delete_origin_interaction_response=AsyncMock(side_effect=delete_original),
        )
        event = SimpleNamespace(
            id="1", token="fake", application_id="2", get_user_id=lambda: "123"
        )
        await discord.defer(bot, event)
        await discord.deliver(bot, event, Result("Records", "Keep this result"))
        public = [m for m in messages.values() if not m["private"] and m.get("embeds")]
        self.assertEqual(
            len(public), 1, "The deferred-response cleanup deleted the actual result"
        )
        self.assertEqual(public[0]["embeds"][0].title, "Records")
        bot.delete_origin_interaction_response.assert_not_awaited()

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
        self.assertEqual(ack.data.flags, MessageFlag(0))
        await discord.deliver(bot, event, Result("Records", "Public result"))
        bot.create_followup_message.assert_not_awaited()
        bot.delete_origin_interaction_response.assert_not_awaited()
        await discord.defer(bot, event, private=True)
        ack = bot.create_interaction_response.call_args.kwargs["response"]
        self.assertEqual(ack.data.flags, MessageFlag.EPHEMERAL)
        await discord.deliver(
            bot, event, Result("Binding", "Private result", private=True)
        )
        self.assertEqual(bot.edit_origin_interaction_response.await_count, 2)

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
            ) as delete,
            patch.object(
                Bot, "edit_origin_interaction_response", AsyncMock(), create=True
            ) as edit,
        ):
            await handle_event(bot, event)
            ack.assert_awaited_once()
            send.assert_not_awaited()
            edit.assert_awaited_once()
            delete.assert_not_awaited()

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
            message = (
                send.call_args.args[1]
                if len(send.call_args.args) > 1
                else send.call_args.kwargs["message"]
            )
            from nonebot.adapters.qq import Message

            self.assertTrue(
                any(segment.type == "file_image" for segment in Message(message)),
                "QQ /help must retain its original help image, not generic Markdown",
            )

    def test_qq_command_panel_uses_original_descriptions(self):
        from src.plugins.gokz.core.command_panel import collect_commands

        commands = collect_commands()
        self.assertEqual(commands[0][0], "/daily")
        panel = {name: description for name, description, _ in commands}
        self.assertEqual(panel["/profile"], "查看玩家资料与链接")
        self.assertEqual(panel["/pb"], "查询地图个人最佳")

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
