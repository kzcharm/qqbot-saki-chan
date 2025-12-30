import asyncio

import aiohttp
from nonebot import logger


async def fetch_json(*urls, params=None, timeout=15, headers=None):
    """
    Fetch JSON data from one or more URLs with error handling.
    
    Args:
        *urls: One or more URLs to fetch
        params: Query parameters
        timeout: Request timeout in seconds
        headers: Optional headers dictionary
    
    Returns:
        JSON data or None if request fails (network/timeout errors)
        For non-200 status codes, returns the error response JSON if available
    """
    async def fetch(session_, url_):
        try:
            async with session_.get(url_, params=params, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    # Try to parse error response as JSON to get detail message
                    try:
                        error_json = await response.json()
                        logger.warning(f"API request failed with status {response.status}: {url_}, error: {error_json.get('detail', '')}")
                        return error_json  # Return error response so caller can check for 'detail'
                    except Exception:
                        # If JSON parsing fails, log and return None
                        error_text = await response.text()
                        logger.warning(f"API request failed with status {response.status}: {url_}, error: {error_text}")
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


async def put_json(url, params=None, timeout=15, headers=None):
    """
    Send PUT request to URL with error handling.
    
    Args:
        url: URL to PUT to
        params: Query parameters
        timeout: Request timeout in seconds
        headers: Optional headers dictionary
    
    Returns:
        JSON data or None if request fails (network/timeout errors)
        For non-200 status codes, returns the error response JSON if available
    """
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.put(url, params=params, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    # Try to parse error response as JSON to get detail message
                    try:
                        error_json = await response.json()
                        logger.warning(f"API PUT request failed with status {response.status}: {url}, error: {error_json.get('detail', '')}")
                        return error_json  # Return error response so caller can check for 'detail'
                    except Exception:
                        # If JSON parsing fails, log and return None
                        error_text = await response.text()
                        logger.warning(f"API PUT request failed with status {response.status}: {url}, error: {error_text}")
                        return None
    except aiohttp.ClientError as e:
        logger.error(f"Network error PUTting {url}: {e}")
        return None
    except asyncio.TimeoutError:
        logger.error(f"PUT request timeout for {url}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error PUTting {url}: {e}")
        return None


async def post_json(url, json_data=None, params=None, timeout=15, headers=None):
    """
    Send POST request to URL with error handling.
    
    Args:
        url: URL to POST to
        json_data: JSON data to send in request body
        params: Query parameters
        timeout: Request timeout in seconds
        headers: Optional headers dictionary
    
    Returns:
        Tuple of (success: bool, data: dict | None, error: str | None)
        - success: True if status is 200/201, False otherwise
        - data: Response JSON data if successful, None otherwise
        - error: Error detail message if available, None otherwise
    """
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.post(url, json=json_data, params=params, headers=headers) as response:
                if response.status in (200, 201):
                    return (True, await response.json(), None)
                else:
                    # Try to parse error response as JSON
                    try:
                        error_json = await response.json()
                        error_detail = error_json.get('detail', '')
                        logger.warning(f"API POST request failed with status {response.status}: {url}, error: {error_detail}")
                        return (False, None, error_detail)
                    except Exception:
                        # If JSON parsing fails, return text
                        error_text = await response.text()
                        logger.warning(f"API POST request failed with status {response.status}: {url}, error: {error_text}")
                        return (False, None, error_text)
    except aiohttp.ClientError as e:
        logger.error(f"Network error POSTing {url}: {e}")
        return (False, None, None)
    except asyncio.TimeoutError:
        logger.error(f"POST request timeout for {url}")
        return (False, None, None)
    except Exception as e:
        logger.error(f"Unexpected error POSTing {url}: {e}")
        return (False, None, None)
