"""Initialize and upgrade the bot database without losing existing bindings."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel


def initialize_database(database_engine: Engine) -> None:
    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).with_name("migrations"))
    )
    with database_engine.connect() as connection:
        # SQLite's default legacy transaction mode does not transact DDL.
        # Start explicitly so a failed table rebuild rolls back atomically.
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            config.attributes["connection"] = connection
            inspector = inspect(connection)
            if not inspector.has_table("qqbot_users"):
                SQLModel.metadata.create_all(connection)
                command.stamp(config, "head")
                connection.commit()
                return
            columns = {
                column["name"] for column in inspector.get_columns("qqbot_users")
            }
            if not inspector.has_table("alembic_version") and not columns.intersection(
                {"game", "cs2kz_mode"}
            ):
                # Fresh installs (and current unversioned schemas) are at head.
                command.stamp(config, "20261026_gokz_only")
                command.upgrade(config, "head")
            else:
                command.upgrade(config, "head")
            SQLModel.metadata.create_all(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
