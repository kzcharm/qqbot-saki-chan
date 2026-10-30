import unittest

import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "request_context", Path(__file__).resolve().parents[1] / "src/plugins/gokz/application/context.py"
)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
RequestContext = module.RequestContext


class RequestContextTests(unittest.TestCase):
    def test_platform_accounts_do_not_collide(self):
        qq = RequestContext("qq", "123")
        discord = RequestContext("discord", "123")
        self.assertNotEqual(qq.storage_key, discord.storage_key)
        self.assertEqual(discord.locale, "en")
        self.assertEqual(qq.locale, "zh-CN")
        self.assertFalse(discord.is_admin)
        self.assertTrue(RequestContext("discord", "123", permissions=frozenset({"root"})).is_admin)
