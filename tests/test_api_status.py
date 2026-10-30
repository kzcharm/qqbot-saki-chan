import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {name: module}):
        spec.loader.exec_module(module)
    return module


global_status = load_module(
    "global_status_under_test", ROOT / "src/plugins/gokz/api/global_status.py"
)


class TestGlobalAPIStatus(unittest.IsolatedAsyncioTestCase):
    async def probe(self, status=200, data=None, error=None):
        response = MagicMock(status=status)
        response.json = AsyncMock(return_value=data)
        if error:
            response.json.side_effect = error
        request = MagicMock()
        request.__aenter__ = AsyncMock(return_value=response)
        session = MagicMock()
        session.get.return_value = request
        session_context = MagicMock()
        session_context.__aenter__ = AsyncMock(return_value=session)
        with (
            patch.object(global_status.aiohttp, "ClientSession", return_value=session_context) as client,
            patch.object(global_status, "perf_counter", side_effect=[10.0, 10.382]),
        ):
            result = await global_status.check_global_api()
        session.get.assert_called_once_with(
            "https://kztimerglobal.com/api/v2/modes", allow_redirects=False
        )
        self.assertEqual(client.call_args.kwargs["timeout"].total, 10)
        self.assertAlmostEqual(result.response_ms, 382)
        return result, response

    async def test_valid_modes_are_available(self):
        result, _ = await self.probe(data=[{"id": 200, "name": "kz_timer"}])
        self.assertTrue(result.available)
        self.assertIsNone(result.error)

    async def test_invalid_data_is_unavailable(self):
        for data in ([], {}, None, "healthy", [1], [{}], [{"id": 200}, None]):
            with self.subTest(data=data):
                result, _ = await self.probe(data=data)
                self.assertFalse(result.available)
                self.assertEqual(result.error, "响应数据无效")

    async def test_http_errors_are_reported_without_reading_body(self):
        for status in (301, 401, 429, 500):
            with self.subTest(status=status):
                result, response = await self.probe(status=status)
                self.assertFalse(result.available)
                self.assertEqual(result.error, f"HTTP {status}")
                response.json.assert_not_awaited()

    async def test_invalid_json_and_content_type(self):
        for error in (
            ValueError("private response body"),
            aiohttp.ContentTypeError(MagicMock(), (), message="private content"),
        ):
            with self.subTest(error=type(error)):
                result, _ = await self.probe(error=error)
                self.assertFalse(result.available)
                self.assertEqual(result.error, "响应数据无效")

    async def test_timeout(self):
        result, _ = await self.probe(error=asyncio.TimeoutError())
        self.assertFalse(result.available)
        self.assertEqual(result.error, "请求超时（10 秒）")

    async def test_connection_failure(self):
        result, _ = await self.probe(error=aiohttp.ClientConnectionError("private details"))
        self.assertFalse(result.available)
        self.assertEqual(result.error, "网络连接失败")

    async def test_failures_when_opening_connection(self):
        for error, reason in (
            (asyncio.TimeoutError(), "请求超时（10 秒）"),
            (aiohttp.ClientConnectionError(), "网络连接失败"),
        ):
            request = MagicMock()
            request.__aenter__ = AsyncMock(side_effect=error)
            session = MagicMock()
            session.get.return_value = request
            context = MagicMock()
            context.__aenter__ = AsyncMock(return_value=session)
            with patch.object(global_status.aiohttp, "ClientSession", return_value=context):
                result = await global_status.check_global_api()
            self.assertFalse(result.available)
            self.assertEqual(result.error, reason)


class TestAPIStatusCommand(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.matcher = MagicMock()
        self.matcher.handle.return_value = lambda handler: handler
        self.matcher.finish = AsyncMock()
        self.register = MagicMock(return_value=self.matcher)
        self.check = AsyncMock()
        async def query(*args):
            return types.SimpleNamespace(data={"status": await self.check()})
        modules = {
            "api_status_tests.presentation.qq_legacy": types.SimpleNamespace(on_command=self.register),
            "nonebot.adapters.qq": types.SimpleNamespace(MessageEvent=object),
            "api_status_tests.presentation.qq_bridge": types.SimpleNamespace(query=query),
            "api_status_tests.application.models": types.SimpleNamespace(CommandInput=lambda: None),
        }
        with patch.dict(sys.modules, modules):
            self.command = load_module(
                "api_status_tests.plugins.api_status",
                ROOT / "src/plugins/gokz/plugins/api_status.py",
            )

    async def test_aliases_and_fresh_private_checks(self):
        self.register.assert_called_once_with("api", aliases={"API"})
        self.check.return_value = global_status.GlobalAPIStatus(True, 382)
        await self.command._(types.SimpleNamespace())
        self.matcher.finish.assert_awaited_once_with(
            "GlobalAPI 状态：🟢 可用\n响应时间：382 ms"
        )
        await self.command._(types.SimpleNamespace())
        self.assertEqual(self.check.await_count, 2)

    async def test_group_failure(self):
        self.check.return_value = global_status.GlobalAPIStatus(False, 393, "HTTP 500")
        await self.command._(types.SimpleNamespace(group_id="group"))
        self.matcher.finish.assert_awaited_once_with(
            "\nGlobalAPI 状态：🔴 不可用\n响应时间：393 ms\n原因：HTTP 500"
        )

    async def test_private_timeout(self):
        self.check.return_value = global_status.GlobalAPIStatus(False, 10001, "请求超时（10 秒）")
        await self.command._(types.SimpleNamespace())
        self.matcher.finish.assert_awaited_once_with(
            "GlobalAPI 状态：🔴 不可用\n响应时间：10001 ms\n原因：请求超时（10 秒）"
        )
