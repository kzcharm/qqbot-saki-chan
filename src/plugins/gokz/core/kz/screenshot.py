import asyncio
import random
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path

import nonebot_plugin_localstore as store
from PIL import Image
from nonebot import require
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from src.plugins.gokz.core.file_oper import check_last_modified_date
from src.plugins.gokz.core.kreedz import format_kzmode
from src.plugins.gokz.core.steam_user import convert_steamid

require("nonebot_plugin_localstore")

executor = ThreadPoolExecutor(max_workers=5)


async def kzgoeu_screenshot_async(steamid, kz_mode, force_update=False):
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        executor, kzgoeu_screenshot, steamid, kz_mode, force_update
    )
    return result


async def vnl_screenshot_async(steamid, force_update=False):
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(executor, vnl_screenshot, steamid, force_update)
    return result


def random_card():
    cache_dir: Path = store.get_cache_dir("plugin_name")
    png_files = list(cache_dir.glob("*.png"))
    if not png_files:
        raise FileNotFoundError("No .png files found in the cache directory")
    random_file = random.choice(png_files)
    return random_file


def kzgoeu_screenshot(steamid, kz_mode, force_update=False):
    steamid = convert_steamid(steamid)
    kz_mode = format_kzmode(kz_mode, 'm')

    steamid64 = convert_steamid(steamid, 64)

    cache_file = store.get_cache_file("plugin_name", f"{steamid64}_{kz_mode}.png")

    # Check last modified date of the file
    if not force_update:
        last_modified_date = check_last_modified_date(cache_file)
        if last_modified_date and (datetime.now() - last_modified_date <= timedelta(hours=1)):
            return str(cache_file)

    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # Run Chrome in headless mode
    options.add_argument("--no-sandbox")  # Bypass OS security model

    driver = webdriver.Chrome(options=options)

    kzgo_url = f"https://kzgo.eu/players/{steamid}?{kz_mode}"
    driver.get(kzgo_url)

    width = 700
    height = 1000
    driver.set_window_size(width, height)

    wait = WebDriverWait(driver, 30)
    wait.until(EC.presence_of_element_located((By.CLASS_NAME, "progress-bg")))
    time.sleep(1)

    screenshot = driver.get_screenshot_as_png()
    driver.quit()
    img = Image.open(BytesIO(screenshot))

    # Crop the image
    left = 90
    top = 100
    right = width - 100
    bottom = height - 280
    cropped_img = img.crop((left, top, right, bottom))

    # Save the cropped screenshot to the cache directory
    cropped_img.save(cache_file)

    return str(cache_file)


def vnl_screenshot(steamid: str, force_update: bool = False) -> str:
    steamid64 = str(convert_steamid(steamid, 64))
    cache_file = store.get_cache_file("plugin_name", f"{steamid64}_kz_vanilla.png")

    # Check last modified date of the file
    if not force_update:
        last_modified_date = check_last_modified_date(cache_file)
        if last_modified_date and (datetime.now() - last_modified_date <= timedelta(days=1)):
            return str(cache_file)

    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    driver = webdriver.Chrome(options=options)

    driver.get(f"https://vnl.kz/#/stats/{steamid64}")
    # Increase window size to capture more content
    width, height = 920, 700
    driver.set_window_size(width, height)
    
    wait = WebDriverWait(driver, 30)
    
    # Wait for the main content to load
    wait.until(EC.presence_of_element_located((By.XPATH, "//p[contains(text(), 'TP')]")))
    
    # Wait for avatar image to load
    try:
        # Wait for the avatar img element to be present
        avatar_img = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "img[src*='avatars.steamstatic.com']")))
        # Wait for the image to be fully loaded
        wait.until(lambda d: d.execute_script(
            "return arguments[0].complete && arguments[0].naturalHeight > 0", 
            avatar_img
        ))
    except Exception:
        # If avatar doesn't load, continue anyway after a short delay
        time.sleep(1)
    
    # Wait for progress bars or other key content elements to be visible
    try:
        wait.until(EC.presence_of_element_located((By.XPATH, "//p[contains(text(), 'PRO')]")))
        # Additional wait for any progress bars to render
        time.sleep(1.5)
    except Exception:
        # If elements don't appear, wait a bit more before screenshot
        time.sleep(2)

    screenshot = driver.get_screenshot_as_png()
    driver.quit()

    img = Image.open(BytesIO(screenshot))
    # Crop: remove top 64px and bottom 130px, keep small side margins
    cropped = img.crop((10, 64, width - 10, height - 130))
    cropped.save(cache_file)
    return str(cache_file)

