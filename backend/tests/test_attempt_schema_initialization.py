import unittest
from unittest.mock import patch

from app.services import ai_sql_attempt_store


class _Result:
    def scalar(self):
        return 1


class _Connection:
    def execute(self, *_args, **_kwargs):
        return _Result()


class _BeginContext:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *_args):
        return False


class _Engine:
    def __init__(self):
        self.begin_calls = 0
        self.connection = _Connection()

    def begin(self):
        self.begin_calls += 1
        return _BeginContext(self.connection)


class AttemptSchemaInitializationTests(unittest.TestCase):
    def test_schema_initialization_runs_once_per_process(self):
        engine = _Engine()
        ai_sql_attempt_store._ATTEMPT_SCHEMA_READY = False
        try:
            with patch.object(ai_sql_attempt_store, "get_engine", return_value=engine):
                ai_sql_attempt_store.ensure_ai_sql_attempts_table()
                ai_sql_attempt_store.ensure_ai_sql_attempts_table()
        finally:
            ai_sql_attempt_store._ATTEMPT_SCHEMA_READY = False

        self.assertEqual(engine.begin_calls, 1)


if __name__ == "__main__":
    unittest.main()
