import os
from pathlib import Path

from sqlmodel import create_engine

from .migration import initialize_database

DATABASE_PATH = Path(os.getenv("BOT_DATABASE_PATH", "data/qqbot.sqlite3"))
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(f"sqlite:///{DATABASE_PATH.resolve()}", connect_args={"check_same_thread": False})


def create_db_and_tables():
    initialize_database(engine)
