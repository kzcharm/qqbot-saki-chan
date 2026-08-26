from datetime import date, datetime, timezone

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel, Column, DateTime, func


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(SQLModel, table=True):
    __tablename__ = 'qqbot_users'
    qid: str = Field(nullable=False, primary_key=True)
    name: str
    steamid: str = Field(nullable=False)
    game: str = Field(nullable=False, default="gokz", max_length=20)
    mode: str = Field(nullable=False, default="kz_timer")
    cs2kz_mode: str = Field(nullable=False, default="classic", max_length=20)
    created_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, default=func.now(), nullable=False))
    updated_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False))


class ComplimentedRun(SQLModel, table=True):
    """A GOKZ record that has claimed its one-time voice compliment."""

    __tablename__ = "qqbot_complimented_runs"

    record_id: int = Field(nullable=False, primary_key=True)
    claimed_at: datetime = Field(
        default_factory=datetime.now,
        sa_column=Column(DateTime, default=func.now(), nullable=False),
    )


class DailyMapAssignment(SQLModel, table=True):
    """An immutable daily-map result for one player and category."""

    __tablename__ = "qqbot_daily_map_assignments"
    __table_args__ = (
        UniqueConstraint("qid", "assignment_date", "daily_type", name="uq_daily_map_assignment"),
    )

    id: int | None = Field(default=None, primary_key=True)
    qid: str = Field(nullable=False, index=True)
    assignment_date: date = Field(nullable=False, index=True)
    daily_type: str = Field(nullable=False, max_length=20)
    mode: str = Field(nullable=False, max_length=10)
    map_id: int = Field(nullable=False)
    map_name: str = Field(nullable=False, max_length=255)
    map_tier: int = Field(nullable=False)
    points: int | None = Field(default=None)
    last_pb_at: datetime | None = Field(default=None, sa_column=Column(DateTime, nullable=True))
    nub_finishers: int = Field(nullable=False, default=0)
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime, default=func.now(), nullable=False),
    )


class DailyMapCache(SQLModel, table=True):
    """Small JSON payload cache for daily-map source data, keyed by scope and kind."""

    __tablename__ = "qqbot_daily_map_cache"

    cache_key: str = Field(primary_key=True, max_length=40)
    payload: str = Field(nullable=False)
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime, default=func.now(), nullable=False),
    )
