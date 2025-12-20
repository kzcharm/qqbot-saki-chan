from datetime import datetime

from sqlmodel import Field, SQLModel, Column, DateTime, func


class User(SQLModel, table=True):
    __tablename__ = 'qqbot_users'
    qid: str = Field(nullable=False, primary_key=True)
    name: str
    steamid: str = Field(nullable=False)
    mode: str = Field(nullable=False, default="kz_timer")
    created_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, default=func.now(), nullable=False))
    updated_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False))


class Leaderboard(SQLModel, table=True):
    steamid: str = Field(primary_key=True, max_length=30)
    name: str | None = Field(default=None, max_length=255)
    pts_skill: float | None = Field(default=None)
    rank_name: str | None = Field(default=None, max_length=30)
    most_played_server: str | None = Field(default=None, max_length=255)
    avatar_hash: str | None = Field(default=None, max_length=255)
    total_points: int | None = Field(default=None)
    count: int | None = Field(default=None)
    pts_avg: int | None = Field(default=None)
    pts_avg_t5: int | None = Field(default=None)
    pts_avg_t6: int | None = Field(default=None)
    pts_avg_t7: int | None = Field(default=None)
    pts_avg_pro: int | None = Field(default=None)
    pts_avg_tp: int | None = Field(default=None)
    count_t5: int | None = Field(default=None)
    count_t6: int | None = Field(default=None)
    count_t7: int | None = Field(default=None)
    count_p1000_tp: int | None = Field(default=None)
    count_p1000_pro: int | None = Field(default=None)
    count_p900: int | None = Field(default=None)
    count_p800: int | None = Field(default=None)
    count_t567_p900: int | None = Field(default=None)
    count_t567_p800: int | None = Field(default=None)
    count_t567_pro: int | None = Field(default=None)
    count_pro: int | None = Field(default=None)
    count_tp: int | None = Field(default=None)
    updated_on: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False))
