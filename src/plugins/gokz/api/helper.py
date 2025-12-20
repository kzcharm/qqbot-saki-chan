import asyncio

import aiohttp
from nonebot import logger


async def fetch_json(*urls, params=None, timeout=15):
    """
    Fetch JSON data from one or more URLs with error handling.
    
    Returns:
        JSON data or None if request fails
    """
    async def fetch(session_, url_):
        try:
            async with session_.get(url_, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.warning(f"API request failed with status {response.status}: {url_}")
                    return None
        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching {url_}: {e}")
            return None
        except asyncio.TimeoutError:
            logger.error(f"Request timeout for {url_}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching {url_}: {e}")
            return None

    if len(urls) == 1:
        url = urls[0]
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            return await fetch(session, url)
    else:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            tasks = [fetch(session, url) for url in urls]
            responses = await asyncio.gather(*tasks)
            return tuple(responses)
