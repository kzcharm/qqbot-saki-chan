"""Capture the website's public player card with bounded browser concurrency."""

import asyncio
import base64
import hashlib
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait

CARD_VERSION = "1"
CACHE_SECONDS = 15 * 60
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="player-card")
_inflight: dict[str, asyncio.Task[str]] = {}


def website_base_url() -> str:
    base = os.getenv("GOKZ_TOP_WEBSITE_URL", "https://gokz.top").rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("GOKZ_TOP_WEBSITE_URL must be an HTTP(S) base URL")
    return base


def capture_player_card(url: str, cache_file: Path) -> str:
    options = webdriver.ChromeOptions()
    for argument in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage", "--window-size=480,1200"):
        options.add_argument(argument)
    driver = webdriver.Chrome(options=options)
    try:
        driver.set_page_load_timeout(45)
        driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
            "width": 480, "height": 1200, "deviceScaleFactor": 2, "mobile": False,
        })
        driver.get(url)

        def ready(current):
            elements = current.find_elements(By.CSS_SELECTOR, '[data-testid="player-card"]')
            if not elements:
                return False
            card = elements[0]
            state = card.get_attribute("data-render-state")
            if state == "error":
                raise RuntimeError("Player card could not be rendered")
            return card if state == "ready" else False

        card = WebDriverWait(driver, 45).until(ready)
        bounds = driver.execute_script(
            "const r = arguments[0].getBoundingClientRect(); return {x:r.x + scrollX,y:r.y + scrollY,width:r.width,height:r.height};", card,
        )
        image = driver.execute_cdp_cmd("Page.captureScreenshot", {
            "format": "png", "captureBeyondViewport": True,
            "clip": {**bounds, "scale": 1},
        })
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_file.with_suffix(".tmp")
        try:
            temporary.write_bytes(base64.b64decode(image["data"]))
            temporary.replace(cache_file)
        finally:
            temporary.unlink(missing_ok=True)
        return str(cache_file)
    finally:
        driver.quit()


async def player_card_screenshot_async(
    steamid64: str, scope: str, cache_dir: Path, force_update: bool = False, lang: str = "zh-CN",
) -> str:
    steamid64 = str(steamid64)
    scope = scope.upper()
    if not re.fullmatch(r"\d{17}", steamid64) or scope not in {"OVR", "KZT", "SKZ", "VNL"}:
        raise ValueError("Invalid player or scope")
    if lang not in {"en", "zh-CN", "ru"}:
        raise ValueError("Invalid card language")
    base = website_base_url()
    origin_key = hashlib.sha256(base.encode()).hexdigest()[:12]
    cache_file = cache_dir / f"player-card-v{CARD_VERSION}-{origin_key}-{steamid64}-{scope}-{lang}.png"
    key = str(cache_file.resolve())
    # Join an existing refresh before considering a previously cached image.
    if key in _inflight:
        return await asyncio.shield(_inflight[key])
    if not force_update and cache_file.is_file() and time.time() - cache_file.stat().st_mtime < CACHE_SECONDS:
        return str(cache_file)

    async def render() -> str:
        url = f"{base}/cards/player/{steamid64}?{urlencode({'scope': scope, 'lang': lang})}"
        return await asyncio.get_running_loop().run_in_executor(_executor, capture_player_card, url, cache_file)

    task = asyncio.create_task(render())
    _inflight[key] = task

    def finished(completed: asyncio.Task[str]) -> None:
        if _inflight.get(key) is completed:
            del _inflight[key]
        # Retrieve errors even when all callers were cancelled.
        if not completed.cancelled():
            completed.exception()

    task.add_done_callback(finished)
    return await asyncio.shield(task)
