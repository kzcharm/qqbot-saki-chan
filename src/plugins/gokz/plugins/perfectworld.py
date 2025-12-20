import aiohttp
from textwrap import dedent
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from src.plugins.gokz.core.command_helper import CommandData
from src.plugins.gokz.core.steam_user import convert_steamid

pw = on_command("pw", aliases={"完美", "perfectworld"})


@pw.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    cd = CommandData(event, args)
    if cd.error:
        return await pw.finish(cd.error)

    steamid64 = convert_steamid(cd.steamid, 64)
    season = "S20"
    if cd.args:
        if cd.args[0].upper().startswith('S'):
            season = str(cd.args[0]).upper()

    url = "https://api.wmpvp.com/api/v2/csgo/pvpDetailDataStats"
    headers = {
        "User-Agent": "okhttp/4.11.0",
        "Content-Type": "application/json",
        "t": str(int(__import__('time').time()))
    }
    payload = {
        "steamId64": steamid64,
        "csgoSeasonId": season
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            resp = await response.json()

    if resp["statusCode"] != 0 or not resp.get("data"):
        return await pw.finish("获取数据失败，请检查SteamID是否正确")

    d = resp["data"]
    history_ratings = d.get("historyPwRatings", [])
    ratings = history_ratings[:5]
    score = d.get("pvpScore", 0)
    match_count = len(history_ratings)

    def get_rank(score: int) -> str:
        if score <= 1000:
            return "D"
        elif score <= 1200:
            return "D+"
        elif score <= 1400:
            return "C"
        elif score <= 1600:
            return "C+"
        elif score <= 1800:
            return "B"
        elif score <= 2000:
            return "B+"
        elif score <= 2200:
            return "A"
        elif score <= 2400:
            return "A+"
        else:
            return "S"

    rank = get_rank(score)
    ratings_avg = sum(ratings) / len(ratings) if ratings else 0

    msg = dedent(f"""
        完美平台数据
        昵称:         {d['name']}
        steamID:   {d['steamId']}
        赛季:         {d['seasonId']}
        当前分数:  {score}（段位：{rank}）
        Rating:      {d['pwRating']}
        总场次:      {match_count}
        平均WE:    {d['avgWe']}
        KD:            {d['kd']}
        胜率:          {d['winRate'] * 100:.1f}%
        RWS:         {d['rws']}
        ADR:         {d['adr']}
        爆头率:     {d['headShotRatio'] * 100:.1f}%
        最近5场Rating: {ratings_avg:.2f}
        {', '.join(f'{r:.2f}' for r in ratings)}
    """).strip()

    await pw.finish(msg)
