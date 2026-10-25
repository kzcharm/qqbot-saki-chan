"""Fresh, credential-free GlobalAPI availability checks."""

import asyncio
from dataclasses import dataclass
from time import perf_counter
from typing import Optional

import aiohttp


GLOBAL_API_MODES_URL = "https://kztimerglobal.com/api/v2/modes"
CHECK_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class GlobalAPIStatus:
    available: bool
    response_ms: float
    error: Optional[str] = None


async def check_global_api() -> GlobalAPIStatus:
    started = perf_counter()
    error = None
    try:
        timeout = aiohttp.ClientTimeout(total=CHECK_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(GLOBAL_API_MODES_URL, allow_redirects=False) as response:
                if response.status != 200:
                    error = f"HTTP {response.status}"
                else:
                    data = await response.json()
                    if not (
                        isinstance(data, list)
                        and data
                        and all(isinstance(mode, dict) and mode for mode in data)
                    ):
                        error = "响应数据无效"
    except asyncio.TimeoutError:
        error = f"请求超时（{CHECK_TIMEOUT_SECONDS} 秒）"
    except (aiohttp.ContentTypeError, ValueError):
        error = "响应数据无效"
    except aiohttp.ClientError:
        error = "网络连接失败"

    return GlobalAPIStatus(
        available=error is None,
        response_ms=(perf_counter() - started) * 1000,
        error=error,
    )
