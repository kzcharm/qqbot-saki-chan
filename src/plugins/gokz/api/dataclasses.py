from dataclasses import dataclass
from typing import Any


@dataclass
class LeaderboardData:
    steamid: str
    name: str
    pts_skill: float
    rank_name: str
    most_played_server: str
    avatar_hash: str
    total_points: int
    count: int
    pts_avg: int
    pts_avg_t5: int
    pts_avg_t6: int
    pts_avg_t7: int
    pts_avg_pro: int
    pts_avg_tp: int
    count_t5: int
    count_t6: int
    count_t7: int
    count_p1000_tp: int
    count_p1000_pro: int
    count_p900: int
    count_p800: int
    count_t567_p900: int
    count_t567_p800: int
    count_t567_pro: int
    count_pro: int
    count_tp: int
    updated_on: str
    rank: int
    percentage: str
    steamid64: str

    @classmethod
    def from_dict(cls, data: dict):
        if data.get("player"):
            return cls.from_v1_leaderboard(data)
        return cls(
            steamid=data.get('steamid'),
            name=data.get('name'),
            pts_skill=data.get('pts_skill'),
            rank_name=data.get('rank_name'),
            most_played_server=data.get('most_played_server'),
            avatar_hash=data.get('avatar_hash'),
            total_points=data.get('total_points'),
            count=data.get('count'),
            pts_avg=data.get('pts_avg'),
            pts_avg_t5=data.get('pts_avg_t5'),
            pts_avg_t6=data.get('pts_avg_t6'),
            pts_avg_t7=data.get('pts_avg_t7'),
            pts_avg_pro=data.get('pts_avg_pro'),
            pts_avg_tp=data.get('pts_avg_tp'),
            count_t5=data.get('count_t5'),
            count_t6=data.get('count_t6'),
            count_t7=data.get('count_t7'),
            count_p1000_tp=data.get('count_p1000_tp'),
            count_p1000_pro=data.get('count_p1000_pro'),
            count_p900=data.get('count_p900'),
            count_p800=data.get('count_p800'),
            count_t567_p900=data.get('count_t567_p900'),
            count_t567_p800=data.get('count_t567_p800'),
            count_t567_pro=data.get('count_t567_pro'),
            count_pro=data.get('count_pro'),
            count_tp=data.get('count_tp'),
            updated_on=data.get('updated_on'),
            rank=data.get('rank'),
            percentage=data.get('percentage'),
            steamid64=data.get('steamid64')
        )

    @classmethod
    def from_player(cls, player: dict[str, Any]):
        steamid64 = str(player.get("steamid64") or "")
        return cls(
            steamid=steamid64, name=player.get("display_name") or player.get("name") or "-",
            pts_skill=0, rank_name="-", most_played_server="-", avatar_hash=player.get("avatar_hash"),
            total_points=0, count=0, pts_avg=0, pts_avg_t5=0, pts_avg_t6=0, pts_avg_t7=0,
            pts_avg_pro=0, pts_avg_tp=0, count_t5=0, count_t6=0, count_t7=0,
            count_p1000_tp=0, count_p1000_pro=0, count_p900=0, count_p800=0,
            count_t567_p900=0, count_t567_p800=0, count_t567_pro=0, count_pro=0,
            count_tp=0, updated_on=player.get("updated_at") or "", rank=0, percentage="-",
            steamid64=steamid64,
        )

    @classmethod
    def from_v1_leaderboard(cls, data: dict[str, Any]):
        player = data.get("player") or {}
        steamid64 = str(player.get("steamid64") or "")
        points = int(data.get("points") or 0)
        count = int(data.get("unique_map_finishes") or 0)
        return cls(
            steamid=steamid64, name=player.get("display_name") or "-",
            pts_skill=round(float(data.get("rating") or 0), 2), rank_name="-", most_played_server="-",
            avatar_hash=None, total_points=points, count=count, pts_avg=points // count if count else 0,
            pts_avg_t5=0, pts_avg_t6=0, pts_avg_t7=0, pts_avg_pro=0, pts_avg_tp=0,
            count_t5=0, count_t6=0, count_t7=0, count_p1000_tp=0, count_p1000_pro=0,
            count_p900=int(data.get("records_900_plus") or 0), count_p800=int(data.get("records_800_plus") or 0),
            count_t567_p900=0, count_t567_p800=0, count_t567_pro=0,
            count_pro=int(data.get("wrs_pro") or 0), count_tp=int(data.get("wrs_nub") or 0),
            updated_on="", rank=int(data.get("rank") or data.get("global_rank") or 0), percentage="-",
            steamid64=steamid64,
        )
