import time

import aiohttp


async def fetch_cs2_stats(steamid: str, season: str = 'S20'):
    url = "https://api.wmpvp.com/api/v2/csgo/pvpDetailDataStats"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "okhttp/4.11.0",
        "t": str(int(time.time()))
    }
    payload = {
        "steamId64": steamid,
        "csgoSeasonId": season
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            data = await response.json()
            return data
