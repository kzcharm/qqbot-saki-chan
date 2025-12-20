import aiohttp
from pathlib import Path
from aiohttp import ClientTimeout

import nonebot_plugin_localstore as store
from nonebot import require

require("nonebot_plugin_localstore")

# CDN URL for GitHub map images
CDN_BASE_URL = "https://cdn.jsdelivr.net/gh/KZGlobalTeam/map-images@public/mediums"


async def get_map_img_url(map_name: str) -> Path:
    """
    Get the path to a cached map image, downloading it from CDN if necessary.
    
    Args:
        map_name: The name of the map (e.g., 'kz_prototype')
        
    Returns:
        Path to the cached image file
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
                    # If download fails, raise an exception
                    raise FileNotFoundError(f"Failed to download map image for {map_name}: HTTP {response.status}")
    except aiohttp.ClientError as e:
        # Network errors - log and re-raise
        from nonebot import logger
        logger.error(f"Network error downloading map image for {map_name}: {e}")
        raise FileNotFoundError(f"Failed to download map image for {map_name}: {e}") from e
    except Exception as e:
        # Other errors - log and re-raise
        from nonebot import logger
        logger.error(f"Error downloading map image for {map_name}: {e}")
        raise
