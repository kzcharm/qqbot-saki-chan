from textwrap import dedent

from nonebot.adapters.qq import Message, MessageEvent
from nonebot.params import CommandArg
from src.plugins.gokz.core.command_helper import CommandData

from ..presentation.qq_bridge import command_input, query
from ..presentation.qq_legacy import on_command

pw = on_command("pw", aliases={"完美", "perfectworld"})


@pw.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    cd = CommandData(event, args)
    if cd.error:
        return await pw.finish(cd.error)

    result = await query(pw, event, "pw", command_input(cd))
    d = result.data["stats"]
    summary = result.data["summary"]
    ratings, score = summary["ratings"], summary["score"]
    match_count, rank = summary["match_count"], summary["rank"]
    ratings_avg = summary["ratings_avg"]

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
