from pathlib import Path

from sqlmodel import SQLModel, create_engine

DATABASE_PATH = Path("data/qqbot.sqlite3")
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(f"sqlite:///{DATABASE_PATH.resolve()}", connect_args={"check_same_thread": False})


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
