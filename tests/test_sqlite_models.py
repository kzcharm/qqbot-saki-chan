import importlib.util
from pathlib import Path
import unittest

from sqlalchemy import inspect
from sqlmodel import SQLModel, Session, create_engine


ROOT = Path(__file__).resolve().parents[1]


def load_models():
    spec = importlib.util.spec_from_file_location("sqlite_models", ROOT / "src/plugins/gokz/db/models.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SQLiteModelsTest(unittest.TestCase):
    def test_user_compliment_and_daily_map_tables_are_created(self):
        models = load_models()
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)

        self.assertEqual(
            inspect(engine).get_table_names(),
            [
                "qqbot_complimented_runs",
                "qqbot_daily_map_assignments",
                "qqbot_daily_map_cache",
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
            session.commit()
            self.assertEqual(session.get(models.User, "qid").steamid, "steamid")
            self.assertIsNotNone(session.get(models.ComplimentedRun, 123))
