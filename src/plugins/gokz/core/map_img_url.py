import aiohttp
from pathlib import Path
from typing import Optional
from aiohttp import ClientTimeout

import nonebot_plugin_localstore as store
from nonebot import require

require("nonebot_plugin_localstore")

# CDN URL for GitHub map images
CDN_BASE_URL = "https://cdn.jsdelivr.net/gh/KZGlobalTeam/map-images@public/mediums"


async def get_map_img_url(map_name: str) -> Optional[Path]:
    """
    Get the path to a cached map image, downloading it from CDN if necessary.
    
    Args:
        map_name: The name of the map (e.g., 'kz_prototype')
        
    Returns:
        Path to the cached image file, or None if unavailable
    """
    cache_file = store.get_cache_file("gokz", f"map_images/{map_name}.jpg")
    
    # Return cached file if it exists
    if cache_file.exists():
        return cache_file
    
    # Download from CDN if not cached
    image_url = f"{CDN_BASE_URL}/{map_name}.jpg"
    
    try:
        async with aiohttp.ClientSession(timeout=ClientTimeout(total=10)) as session:
            async with session.get(image_url) as response:
                if response.status == 200:
                    # Ensure parent directory exists
                    cache_file.parent.mkdir(parents=True, exist_ok=True)
                    # Download and save the image
                    with cache_file.open("wb") as f:
                        f.write(await response.read())
                    return cache_file
                else:
                    from nonebot import logger
                    logger.info(
                        f"Map image not available for {map_name}: HTTP {response.status}"
                    )
                    return None
    except aiohttp.ClientError as e:
        # Network errors - log and return None
        from nonebot import logger
        logger.info(f"Network error downloading map image for {map_name}: {e}")
        return None
    except Exception as e:
        # Other errors - log and re-raise
        from nonebot import logger
        logger.error(f"Error downloading map image for {map_name}: {e}")
        raise


def get_cs2kz_preferred_map_img_url(map_name: str) -> str:
    if map_name == "kz_sonder":
        return f"https://raw.githubusercontent.com/vap222222/nonglobalmaps/main/{map_name}.jpg"
    return f"https://raw.githubusercontent.com/kzglobalteam/cs2kz-images/public/webp/medium/{map_name}/1.webp"


async def get_cs2kz_preferred_map_img_path(map_name: str) -> Optional[Path]:
    """Cache a CS2KZ map image locally so QQ uploads the file directly."""
    image_url = get_cs2kz_preferred_map_img_url(map_name)
    extension = ".jpg" if map_name == "kz_sonder" else ".webp"
    cache_file = store.get_cache_file("gokz", f"cs2kz_map_images/{map_name}{extension}")

    if cache_file.exists():
        return cache_file

    try:
        async with aiohttp.ClientSession(timeout=ClientTimeout(total=10)) as session:
            async with session.get(image_url) as response:
                if response.status != 200:
                    from nonebot import logger
                    logger.info(f"CS2KZ map image not available for {map_name}: HTTP {response.status}")
                    return None
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                with cache_file.open("wb") as f:
                    f.write(await response.read())
                return cache_file
    except aiohttp.ClientError as e:
        from nonebot import logger
        logger.info(f"Network error downloading CS2KZ map image for {map_name}: {e}")
        return None
    except Exception as e:
        from nonebot import logger
        logger.error(f"Error caching CS2KZ map image for {map_name}: {e}")
        return None
