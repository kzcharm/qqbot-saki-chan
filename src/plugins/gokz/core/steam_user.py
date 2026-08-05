import asyncio

import aiohttp
from aiohttp import ClientTimeout
from steam.steamid import SteamID, from_url

from nonebot import logger

from src.plugins.gokz.config import STEAM_API_KEY


def convert_steamid(steamid, target_type: int | str = 64, url=False):
    logger.debug(f"Converting SteamID: {steamid} to type: {target_type}")
    steamid = SteamID(steamid)
    if steamid.is_valid() is False:
        raise ValueError(f"Invalid SteamID: {steamid}")

    if url:
        return steamid.community_url

    if target_type == '64':
        return str(steamid.as_64)

    target_type = int(target_type)

    if target_type == 2:
        return steamid.as_steam2
    if target_type == 3:
        return steamid.as_steam3
    if target_type == 32:
        return steamid.as_32
    if target_type == 64:
        return str(steamid.as_64)
    if target_type == 0:
        return {
            "steam2": steamid.as_steam2,
            "steam3": steamid.as_steam3,
            "steam64": str(steamid.as_64),
            "steam32": steamid.as_32,
            "url": steamid.community_url,
        }

    raise ValueError(f"Invalid target type: {target_type}")


async def retrieve_steamid(steamid_or_url) -> str | None:
    logger.debug(f"Retrieving SteamID from: {steamid_or_url}")
    steamid_or_url = str(steamid_or_url).strip()
    if steamid_or_url.startswith("http"):
        if "/profiles/" in steamid_or_url:
            steam64 = steamid_or_url.split("/profiles/")[-1]
            steamid = SteamID(steam64)
            if steamid.is_valid():
                return str(steamid.as_64)
            else:
                return None

        elif "/id/" in steamid_or_url:
            steamid = from_url(steamid_or_url)
            return str(steamid.as_64) if steamid and steamid.is_valid() else None

        else:
            return None

    else:
        return convert_steamid(steamid_or_url, 64)


async def check_steam_bans(steamid) -> dict | None:
    steam64 = convert_steamid(steamid, 64)

    url = f'http://api.steampowered.com/ISteamUser/GetPlayerBans/v1/?key={STEAM_API_KEY}&steamids={steam64}'

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            ban_data = await response.json()
    return ban_data['players'][0]


async def get_steam_user_info(steamid, timeout=5.0) -> dict | None:
    """
        Get information about a Steam user using their SteamID64.
        Returns:
            {
                'steamid': str,
                'communityvisibilitystate': int,
                'profilestate': int,
                'personaname': str,
                'commentpermission': int,
                'profileurl': str,
                'avatar': str,
                'avatarmedium': str,
                'avatarfull': str,
                'avatarhash': str,
                'lastlogoff': int,
                'personastate': int,
                'primaryclanid': str,
                'timecreated': int,
                'personastateflags': int,
                'loccountrycode': str,
                'locstatecode': str,
                'loccityid': int
            }
    """
    steamid = convert_steamid(steamid, 64)

    url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={STEAM_API_KEY}&steamids={steamid}"

    try:
        async with aiohttp.ClientSession(timeout=ClientTimeout(timeout)) as session:
            async with session.get(url) as response:
                try:
                    data = await response.json()
                except aiohttp.client_exceptions.ContentTypeError:
                    logger.warning(f"Failed to get user info for SteamID: {steamid}")
                    return None
    except asyncio.TimeoutError:
        logger.warning(f"Request to Steam API timed out for SteamID: {steamid}")
        return {"error": "Request timed out"}

    try:
        player_data = data['response']['players'][0]
        return player_data
    except IndexError:
        logger.warning(f"Failed to get user info for SteamID: {steamid}")
        return None
