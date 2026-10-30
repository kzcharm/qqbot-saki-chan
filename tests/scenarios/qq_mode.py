"""QQ mode presentation exercises the real shared preference service."""

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

nonebot.init(_env_file=None, driver="~httpx+~websockets", log_level="ERROR")
assert nonebot.load_plugin("src.plugins.gokz")
from nonebot.adapters.qq import Message
from sqlmodel import Session
from src.plugins.gokz.application import service
from src.plugins.gokz.core.binding_message import binding_help_message
from src.plugins.gokz.core.mode_message import mode_selection_message
from src.plugins.gokz.db.models import User
from src.plugins.gokz.plugins import general


class Finished(BaseException):
    pass


class ModeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        with Session(service.engine) as session:
            user = session.get(User, "mode-test")
            if user:
                session.delete(user)
                session.commit()
            session.add(
                User(
                    qid="mode-test",
                    steamid="76561197960278073",
                    name="Player",
                    mode="kz_simple",
                )
            )
            session.commit()

    async def call(self, value):
        event = SimpleNamespace(get_user_id=lambda: "mode-test")
        finish = AsyncMock(side_effect=Finished)
        with patch.object(general.mode, "finish", finish), self.assertRaises(Finished):
            await general.update_mode(event, Message(value))
        return finish.call_args.args[0]

    def saved_mode(self):
        with Session(service.engine) as session:
            return session.get(User, "mode-test").mode

    async def test_picker_uses_saved_mode(self):
        self.assertEqual(await self.call(""), mode_selection_message("SKZ"))
        self.assertEqual(self.saved_mode(), "kz_simple")

    async def test_modes_save_through_shared_service(self):
        for mode in ("OVR", "KZT", "SKZ", "VNL"):
            self.assertEqual(
                await self.call(mode.lower()), mode_selection_message(mode)
            )
            self.assertEqual(self.saved_mode(), mode)

    async def test_invalid_modes_do_not_write(self):
        for value in ("gokz kzt", "cs2kz vanilla", "classic", "ckz"):
            self.assertEqual(await self.call(value), "模式格式不正确")
            self.assertEqual(self.saved_mode(), "kz_simple")

    async def test_unbound_user_gets_original_help(self):
        with Session(service.engine) as session:
            session.delete(session.get(User, "mode-test"))
            session.commit()
        self.assertEqual(await self.call("KZT"), binding_help_message())


if __name__ == "__main__":
    unittest.main()
