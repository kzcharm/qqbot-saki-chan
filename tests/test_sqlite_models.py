import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

from sqlalchemy import inspect, text
from sqlmodel import SQLModel, Session, create_engine


ROOT = Path(__file__).resolve().parents[1]


def load_models():
    spec = importlib.util.spec_from_file_location("sqlite_models", ROOT / "src/plugins/gokz/db/models.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SQLiteModelsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.models = load_models()
        spec = importlib.util.spec_from_file_location("database_migration", ROOT / "src/plugins/gokz/db/migration.py")
        cls.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.migration)

    def test_user_compliment_and_daily_map_tables_are_created(self):
        models = self.models
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)

        self.assertEqual(
            inspect(engine).get_table_names(),
            [
                "bot_platform_preferences",
                "qqbot_complimented_runs",
                "qqbot_daily_map_assignments",
                "qqbot_daily_map_cache",
                "qqbot_group_server_settings",
                "qqbot_users",
            ],
        )
        self.assertEqual(
            inspect(engine).get_unique_constraints("qqbot_daily_map_assignments")[0]["column_names"],
            ["qid", "assignment_date", "daily_type"],
        )

        with Session(engine) as session:
            session.add(models.User(qid="qid", name="name", steamid="steamid"))
            session.add(models.ComplimentedRun(record_id=123))
            session.add(models.GroupServerSetting(group_id="group", server_group="axekz"))
            session.commit()
            self.assertEqual(session.get(models.User, "qid").steamid, "steamid")
            self.assertIsNotNone(session.get(models.ComplimentedRun, 123))
            self.assertEqual(session.get(models.GroupServerSetting, "group").server_group, "axekz")


    def test_fresh_database_and_repeated_startup(self):
        engine = create_engine("sqlite://")
        self.migration.initialize_database(engine)
        self.migration.initialize_database(engine)
        self.assert_user_schema(engine)
        self.assert_binding_insert(engine)

    def test_existing_current_unversioned_database(self):
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine, tables=[t for t in SQLModel.metadata.sorted_tables if t.name != "bot_platform_preferences"])
        self.migration.initialize_database(engine)
        self.assert_user_schema(engine)
        self.assert_binding_insert(engine)

    def legacy_database(self):
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE qqbot_users (
                    qid VARCHAR NOT NULL PRIMARY KEY, name VARCHAR NOT NULL,
                    steamid VARCHAR NOT NULL, game VARCHAR(20) NOT NULL,
                    mode VARCHAR NOT NULL, cs2kz_mode VARCHAR(20) NOT NULL,
                    created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
                )
            """))
            for qid, game, mode in (("1", "gokz", "SKZ"), ("2", "cs2kz", "kz_timer")):
                connection.execute(text("""
                    INSERT INTO qqbot_users VALUES
                    (:qid, '玩家', :steamid, :game, :mode, 'vanilla',
                     '2026-01-01 12:00:00', '2026-02-01 13:00:00')
                """), dict(qid=qid, steamid="7656119800000000" + qid, game=game, mode=mode))
        return engine

    def test_legacy_upgrade_preserves_bindings_modes_and_timestamps(self):
        engine = self.legacy_database()
        columns = "qid, name, steamid, mode, created_at, updated_at"
        with engine.connect() as connection:
            before = connection.execute(text(f"SELECT {columns} FROM qqbot_users ORDER BY qid")).all()
        self.migration.initialize_database(engine)
        self.migration.initialize_database(engine)
        self.assert_user_schema(engine)
        with engine.connect() as connection:
            self.assertEqual(connection.execute(text(f"SELECT {columns} FROM qqbot_users ORDER BY qid")).all(), before)
        self.assert_binding_insert(engine)

    def test_failed_migration_rolls_back_and_can_retry(self):
        engine = self.legacy_database()
        original = self.migration.command.upgrade

        def fail_after_rebuild(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("simulated migration failure")

        with patch.object(self.migration.command, "upgrade", fail_after_rebuild):
            with self.assertRaises(RuntimeError):
                self.migration.initialize_database(engine)
        self.assertIn("game", {column["name"] for column in inspect(engine).get_columns("qqbot_users")})
        with engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT count(*) FROM qqbot_users")).scalar(), 2)
        self.migration.initialize_database(engine)
        self.assert_user_schema(engine)

    def assert_user_schema(self, engine):
        self.assertEqual(
            {column["name"] for column in inspect(engine).get_columns("qqbot_users")},
            {"qid", "name", "steamid", "mode", "created_at", "updated_at"},
        )
        with engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT version_num FROM alembic_version")).scalar(), "828560602427")

    def assert_binding_insert(self, engine):
        with Session(engine) as session:
            session.add(self.models.User(qid="new", name="New player", steamid="76561198000000003"))
            session.commit()
            user = session.get(self.models.User, "new")
            self.assertEqual(user.mode, "kz_timer")
            user.mode = "VNL"
            session.commit()
            self.assertEqual(session.get(self.models.User, "new").mode, "VNL")
