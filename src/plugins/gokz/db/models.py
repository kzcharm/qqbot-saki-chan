from datetime import datetime

from sqlmodel import Field, SQLModel, Column, DateTime, func


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
