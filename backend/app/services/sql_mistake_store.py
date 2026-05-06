import re
import sys
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from app.db import get_engine

MISTAKE_TYPES = {
    "invalid_table",
    "invalid_column",
    "missing_limit",
    "dangerous_query",
    "syntax_error",
    "multiple_statements",
    "unclear_question",
    "wrong_join",
    "wrong_filter",
    "wrong_aggregation",
    "permission_denied",
    "unknown",
}


def ensure_sql_mistake_examples_table() -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS sql_mistake_examples (
        id VARCHAR(36) PRIMARY KEY,
        query_attempt_id VARCHAR(36) NOT NULL,
        user_question TEXT NOT NULL,
        wrong_sql LONGTEXT NULL,
        validator_feedback LONGTEXT NULL,
        validation_reason LONGTEXT NULL,
        mistake_type VARCHAR(50) NOT NULL,
        corrected_sql LONGTEXT NULL,
        final_correct_sql LONGTEXT NULL,
        risk_level VARCHAR(20) NOT NULL,
        created_at DATETIME NOT NULL
    )
    """
    with get_engine().begin() as conn:
        conn.execute(text(ddl))


def create_mistake_example(
    query_attempt_id: str,
    user_question: str,
    wrong_sql: str | None,
    validator_feedback: str,
    validation_reason: str,
    mistake_type: str,
    risk_level: str,
    corrected_sql: str | None = None,
    final_correct_sql: str | None = None,
) -> str:
    ensure_sql_mistake_examples_table()
    mistake_id = str(uuid4())
    normalized_type = mistake_type if mistake_type in MISTAKE_TYPES else "unknown"
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO sql_mistake_examples (
                    id, query_attempt_id, user_question, wrong_sql, validator_feedback,
                    validation_reason, mistake_type, corrected_sql, final_correct_sql,
                    risk_level, created_at
                ) VALUES (
                    :id, :query_attempt_id, :user_question, :wrong_sql, :validator_feedback,
                    :validation_reason, :mistake_type, :corrected_sql, :final_correct_sql,
                    :risk_level, :created_at
                )
                """
            ),
            {
                "id": mistake_id,
                "query_attempt_id": query_attempt_id,
                "user_question": user_question,
                "wrong_sql": wrong_sql,
                "validator_feedback": validator_feedback,
                "validation_reason": validation_reason,
                "mistake_type": normalized_type,
                "corrected_sql": corrected_sql,
                "final_correct_sql": final_correct_sql,
                "risk_level": risk_level,
                "created_at": _now(),
            },
        )
    _console_log("MISTAKE_EXAMPLE_CREATED", {"attemptId": query_attempt_id, "mistakeType": normalized_type})
    return mistake_id


def update_attempt_mistakes_with_final_sql(query_attempt_id: str, final_correct_sql: str) -> None:
    ensure_sql_mistake_examples_table()
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                UPDATE sql_mistake_examples
                SET final_correct_sql = :final_correct_sql
                WHERE query_attempt_id = :query_attempt_id
                  AND final_correct_sql IS NULL
                """
            ),
            {"query_attempt_id": query_attempt_id, "final_correct_sql": final_correct_sql},
        )


def list_mistake_examples(limit: int = 100) -> list[dict[str, Any]]:
    ensure_sql_mistake_examples_table()
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT * FROM sql_mistake_examples
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()
    return [dict(row) for row in rows]


def similar_mistake_examples(question: str, limit: int = 3) -> list[dict[str, str]]:
    mistakes = [
        mistake for mistake in list_mistake_examples(200)
        if mistake.get("validator_feedback") or mistake.get("corrected_sql") or mistake.get("final_correct_sql")
    ]
    scored = [
        (_token_similarity(question, str(mistake.get("user_question") or "")), mistake)
        for mistake in mistakes
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    results = [
        {
            "user_question": str(mistake.get("user_question") or ""),
            "wrong_sql": str(mistake.get("wrong_sql") or ""),
            "reason": str(mistake.get("validation_reason") or mistake.get("validator_feedback") or ""),
            "correct_sql": str(mistake.get("corrected_sql") or mistake.get("final_correct_sql") or ""),
        }
        for score, mistake in scored[:limit]
        if score >= 0.18
    ]
    _console_log("SIMILAR_MISTAKES_FOUND", {"count": len(results)})
    return results


def _token_similarity(left: str, right: str) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0
    return len(left_tokens & right_tokens) / max(len(left_tokens | right_tokens), 1)


def _tokens(value: str) -> set[str]:
    stop_words = {"the", "and", "for", "with", "show", "give", "report", "list", "all"}
    return {
        token for token in re.findall(r"[a-z0-9_]+", value.lower())
        if len(token) > 2 and token not in stop_words
    }


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _console_log(event: str, payload: dict[str, Any]) -> None:
    rendered = ", ".join(f"{key}={value}" for key, value in payload.items())
    sys.stderr.write(f"[AI-SQL][{event}] {rendered}\n")
    sys.stderr.flush()
