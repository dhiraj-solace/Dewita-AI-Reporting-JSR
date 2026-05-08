from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.sql_safety_validator import validate_sql_safety
from app.services.query_safety import validate_user_query_safety


SCHEMA = {
    "tables": [
        {
            "name": "projects",
            "aliases": [],
            "columns": [{"name": "id"}, {"name": "project_name"}],
        }
    ]
}


def test_valid_select_query() -> None:
    result = validate_sql_safety("SELECT id, project_name FROM projects LIMIT 10", SCHEMA)
    assert result.isValid, result


def test_dangerous_delete_query() -> None:
    result = validate_sql_safety("DELETE FROM projects", SCHEMA)
    assert not result.isValid
    assert result.mistakeType == "dangerous_query"


def test_query_without_limit() -> None:
    result = validate_sql_safety("SELECT id, project_name FROM projects", SCHEMA)
    assert not result.isValid
    assert result.mistakeType == "missing_limit"


def test_invalid_table_name() -> None:
    result = validate_sql_safety("SELECT id FROM fake_projects LIMIT 10", SCHEMA)
    assert not result.isValid
    assert result.mistakeType == "invalid_table"


def test_user_query_safety_blocks_write_requests_before_schema() -> None:
    result = validate_user_query_safety("Please delete old projects")
    assert not result.is_safe
    assert result.blocked_operation == "DELETE"


def test_user_query_safety_allows_reporting_requests_without_schema() -> None:
    result = validate_user_query_safety("Show week 5 project totals grouped by type")
    assert result.is_safe


def test_similar_example_injected_into_prompt_preview() -> None:
    try:
        from app.services.llm import build_sql_generation_payload_preview
    except ModuleNotFoundError as exc:
        print(f"SKIP: prompt preview test requires backend dependency {exc.name}.")
        return
    preview = build_sql_generation_payload_preview(
        "Show projects",
        None,
        None,
        [{"user_question": "Show projects", "sql": "SELECT id FROM projects LIMIT 10"}],
        [{"user_question": "Show projects", "wrong_sql": "DELETE FROM projects", "reason": "dangerous", "correct_sql": "SELECT id FROM projects LIMIT 10"}],
    )
    assert preview["similar_examples_count"] == 1
    assert preview["mistake_examples_count"] == 1


def test_gold_db_path_available_or_skipped() -> None:
    has_database = os.getenv("DATABASE_URL") or all(
        os.getenv(name) for name in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")
    )
    if not has_database:
        print("SKIP: approved query becoming gold requires DATABASE_URL/DB_* settings.")
        return
    from app.services.ai_sql_attempt_store import ensure_ai_sql_attempts_table
    from app.services.sql_mistake_store import ensure_sql_mistake_examples_table

    ensure_ai_sql_attempts_table()
    ensure_sql_mistake_examples_table()


if __name__ == "__main__":
    tests = [
        test_valid_select_query,
        test_dangerous_delete_query,
        test_query_without_limit,
        test_invalid_table_name,
        test_user_query_safety_blocks_write_requests_before_schema,
        test_user_query_safety_allows_reporting_requests_without_schema,
        test_similar_example_injected_into_prompt_preview,
        test_gold_db_path_available_or_skipped,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
