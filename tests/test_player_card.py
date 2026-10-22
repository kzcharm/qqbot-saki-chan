import asyncio
import base64
import importlib.util
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SPEC = importlib.util.spec_from_file_location("player_card_under_test", Path(__file__).resolve().parents[1] / "src/plugins/gokz/core/kz/player_card.py")
card = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(card)
PLAYER = "76561198000000001"


class PlayerCardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.cache = Path(self.directory.name)
        self.env = patch.dict(os.environ, {"GOKZ_TOP_WEBSITE_URL": "https://example.test"})
        self.env.start()

    async def asyncTearDown(self):
        self.env.stop()
        self.directory.cleanup()

    def render(self, url, path):
        path.write_bytes(b"image")
        return str(path)

    async def test_cache_refresh_and_key_separation(self):
        with patch.object(card, "capture_player_card", side_effect=self.render) as render:
            first = await card.player_card_screenshot_async(PLAYER, "OVR", self.cache)
            self.assertEqual(first, await card.player_card_screenshot_async(PLAYER, "OVR", self.cache))
            self.assertEqual(render.call_count, 1)
            await card.player_card_screenshot_async(PLAYER, "OVR", self.cache, force_update=True)
            self.assertEqual(render.call_count, 2)
            await card.player_card_screenshot_async(PLAYER, "VNL", self.cache)
            await card.player_card_screenshot_async(PLAYER, "OVR", self.cache, lang="en")
            self.assertEqual(render.call_count, 4)
            os.utime(first, (time.time() - 901, time.time() - 901))
            await card.player_card_screenshot_async(PLAYER, "OVR", self.cache)
            self.assertEqual(render.call_count, 5)
            self.assertIn("scope=OVR", render.call_args.args[0])

    async def test_deduplicates_and_survives_cancelled_caller(self):
        started, release = threading.Event(), threading.Event()
        def render(url, path):
            started.set()
            release.wait(5)
            return self.render(url, path)
        with patch.object(card, "capture_player_card", side_effect=render) as capture:
            first = asyncio.create_task(card.player_card_screenshot_async(PLAYER, "OVR", self.cache))
            await asyncio.to_thread(started.wait, 5)
            second = asyncio.create_task(card.player_card_screenshot_async(PLAYER, "OVR", self.cache, force_update=True))
            await asyncio.sleep(0)
            first.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await first
            release.set()
            self.assertTrue(Path(await second).exists())
            self.assertEqual(capture.call_count, 1)

    async def test_limits_concurrent_browsers(self):
        active = peak = 0
        lock = threading.Lock()
        def render(url, path):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.05)
            result = self.render(url, path)
            with lock:
                active -= 1
            return result
        with patch.object(card, "capture_player_card", side_effect=render):
            await asyncio.gather(*(card.player_card_screenshot_async(PLAYER, scope, self.cache) for scope in ["OVR", "KZT", "SKZ", "VNL"]))
        self.assertEqual(peak, 2)

    async def test_failures_are_not_cached_and_can_retry(self):
        with patch.object(card, "capture_player_card", side_effect=RuntimeError("failed")):
            with self.assertRaises(RuntimeError):
                await card.player_card_screenshot_async(PLAYER, "OVR", self.cache)
        self.assertEqual(list(self.cache.iterdir()), [])
        with patch.object(card, "capture_player_card", side_effect=self.render):
            self.assertTrue(Path(await card.player_card_screenshot_async(PLAYER, "OVR", self.cache)).exists())

    async def test_invalid_input_does_not_start_browser(self):
        with patch.object(card, "capture_player_card") as capture:
            with self.assertRaises(ValueError):
                await card.player_card_screenshot_async("../bad", "OVR", self.cache)
            capture.assert_not_called()


class BrowserCleanupTests(unittest.TestCase):
    def test_browser_quits_after_page_failure(self):
        driver = MagicMock()
        driver.get.side_effect = RuntimeError("navigation failed")
        with patch.object(card.webdriver, "Chrome", return_value=driver):
            with self.assertRaises(RuntimeError):
                card.capture_player_card("https://example.test", Path("unused.png"))
        driver.quit.assert_called_once()

    def test_ready_element_is_captured_at_double_resolution(self):
        driver = MagicMock()
        element = MagicMock()
        element.get_attribute.return_value = "ready"
        driver.find_elements.return_value = [element]
        bounds = {"x": 0, "y": 0, "width": 480, "height": 950}
        driver.execute_script.return_value = bounds
        driver.execute_cdp_cmd.return_value = {"data": base64.b64encode(b"png").decode()}
        with tempfile.TemporaryDirectory() as directory, patch.object(card.webdriver, "Chrome", return_value=driver):
            result = Path(card.capture_player_card("https://example.test", Path(directory) / "card.png"))
            self.assertEqual(result.read_bytes(), b"png")
        self.assertEqual(driver.execute_cdp_cmd.call_args_list[0].args[1]["deviceScaleFactor"], 2)
        self.assertEqual(driver.execute_cdp_cmd.call_args.args[1]["clip"], {**bounds, "scale": 1})
        driver.quit.assert_called_once()

    def test_error_state_stops_capture(self):
        driver = MagicMock()
        element = MagicMock()
        element.get_attribute.return_value = "error"
        driver.find_elements.return_value = [element]
        with patch.object(card.webdriver, "Chrome", return_value=driver):
            with self.assertRaises(RuntimeError):
                card.capture_player_card("https://example.test", Path("unused.png"))
        driver.quit.assert_called_once()
