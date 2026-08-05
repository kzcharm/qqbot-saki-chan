import os
import urllib.parse

from dotenv import load_dotenv
from sqlalchemy import inspect, text
from sqlmodel import SQLModel, create_engine

load_dotenv()


def get_url():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    user = os.getenv("MYSQL_USER", "root")
    password = urllib.parse.quote_plus(os.getenv("MYSQL_PASSWORD", ""))
    server = os.getenv("MYSQL_SERVER", "localhost")
    port = os.getenv("MYSQL_PORT", "3306")
    db_name = os.getenv("MYSQL_DB", "app")
    return f"mysql+pymysql://{user}:{password}@{server}:{port}/{db_name}"


engine = create_engine(get_url())


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
    migrate_user_defaults()


def migrate_user_defaults():
    inspector = inspect(engine)
    if not inspector.has_table("qqbot_users"):
        return

    columns = {column["name"] for column in inspector.get_columns("qqbot_users")}
    statements = []
    if "game" not in columns:
        statements.append("ALTER TABLE qqbot_users ADD COLUMN game VARCHAR(20) NOT NULL DEFAULT 'gokz'")
    if "cs2kz_mode" not in columns:
        statements.append("ALTER TABLE qqbot_users ADD COLUMN cs2kz_mode VARCHAR(20) NOT NULL DEFAULT 'classic'")

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def init_db():
    pass


if __name__ == '__main__':
    print(get_url())
    create_db_and_tables()
