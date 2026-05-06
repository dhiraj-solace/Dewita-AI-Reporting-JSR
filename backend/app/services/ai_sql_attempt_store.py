import json
import re
import sys
from time import perf_counter
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from app.db import get_engine
from app.services.gold_vector_store import search_gold_examples, upsert_gold_example
from app.services.sql_guard import validate_select_sql


ATTEMPT_FIELDS = (
    "id",
    "user_question",
    "schema_snapshot",
    "generated_sql",
    "validator_status",
    "validator_feedback",
    "regenerated_sql",
    "final_sql",
    "execution_status",
    "execution_error",
    "result_row_count",
    "user_feedback_status",
    "admin_approved",
    "is_gold_example",
    "created_at",
    "updated_at",
)

_VECTOR_SYNCED_ONCE = False


def ensure_ai_sql_attempts_table() -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS ai_sql_attempts (
        id VARCHAR(36) PRIMARY KEY,
        user_question TEXT NOT NULL,
        schema_snapshot LONGTEXT NULL,
        generated_sql LONGTEXT NULL,
        validator_status VARCHAR(50) NULL,
        validator_feedback LONGTEXT NULL,
        regenerated_sql LONGTEXT NULL,
        final_sql LONGTEXT NULL,
        execution_status VARCHAR(50) NULL,
        execution_error LONGTEXT NULL,
        result_row_count INT NULL,
        user_feedback_status VARCHAR(50) NULL,
        admin_approved BOOLEAN NOT NULL DEFAULT FALSE,
        is_gold_example BOOLEAN NOT NULL DEFAULT FALSE,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL
    )
    """
    with get_engine().begin() as conn:
        conn.execute(text(ddl))


def create_attempt(user_question: str, schema_snapshot: dict[str, Any]) -> str:
    ensure_ai_sql_attempts_table()
    attempt_id = str(uuid4())
    now = _now()
    payload = {
        "id": attempt_id,
        "user_question": user_question,
        "schema_snapshot": json.dumps(schema_snapshot, ensure_ascii=False, default=str),
        "created_at": now,
        "updated_at": now,
    }
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO ai_sql_attempts (
                    id, user_question, schema_snapshot, created_at, updated_at
                ) VALUES (
                    :id, :user_question, :schema_snapshot, :created_at, :updated_at
                )
                """
            ),
            payload,
        )
    return attempt_id


def update_attempt(attempt_id: str, **fields: Any) -> None:
    allowed = set(ATTEMPT_FIELDS) - {"id", "created_at", "updated_at"}
    updates = {key: _serialize_value(value) for key, value in fields.items() if key in allowed}
    if not updates:
        return
    updates["updated_at"] = _now()
    assignments = ", ".join(f"{key} = :{key}" for key in updates)
    updates["id"] = attempt_id
    with get_engine().begin() as conn:
        conn.execute(text(f"UPDATE ai_sql_attempts SET {assignments} WHERE id = :id"), updates)


def get_attempt(attempt_id: str) -> dict[str, Any] | None:
    ensure_ai_sql_attempts_table()
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT * FROM ai_sql_attempts WHERE id = :id"),
            {"id": attempt_id},
        ).mappings().first()
    return _row_to_dict(row) if row else None


def list_attempts(limit: int = 50, gold_only: bool = False) -> list[dict[str, Any]]:
    ensure_ai_sql_attempts_table()
    where = "WHERE is_gold_example = TRUE" if gold_only else ""
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT * FROM ai_sql_attempts
                {where}
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()
    return [_row_to_dict(row) for row in rows]


def review_attempt(attempt_id: str, user_feedback_status: str, admin_approved: bool) -> dict[str, Any]:
    attempt = get_attempt(attempt_id)
    if not attempt:
        raise ValueError("AI SQL attempt was not found.")

    is_gold_example = _is_gold_eligible(attempt, user_feedback_status, admin_approved)
    _console_attempt_log(
        attempt_id,
        "admin",
        f"user_feedback_status={user_feedback_status} admin_approved={admin_approved}",
    )
    update_attempt(
        attempt_id,
        user_feedback_status=user_feedback_status,
        admin_approved=admin_approved,
        is_gold_example=is_gold_example,
    )
    _console_attempt_log(attempt_id, "gold", f"is_gold_example={is_gold_example}")
    reviewed = get_attempt(attempt_id)
    if reviewed is None:
        raise ValueError("AI SQL attempt was not found after review.")
    if is_gold_example:
        try:
            upsert_gold_example(reviewed)
            _console_attempt_log(attempt_id, "vector", "gold example upserted into vector DB")
        except Exception as exc:
            _console_attempt_log(attempt_id, "vector", f"vector DB upsert skipped: {exc}")
    return reviewed


def similar_gold_examples(
    question: str,
    limit: int = 3,
    attempt_id: str | None = None,
) -> tuple[list[dict[str, str]], str]:
    global _VECTOR_SYNCED_ONCE
    examples = list_attempts(limit=200, gold_only=True)
    try:
        started = perf_counter()
        if not _VECTOR_SYNCED_ONCE:
            for example in examples:
                upsert_gold_example(example)
            _VECTOR_SYNCED_ONCE = True
            if attempt_id:
                _console_attempt_log(attempt_id, "vector", f"synced {len(examples)} gold examples into vector DB")
        vector_examples = search_gold_examples(question, limit)
        if attempt_id:
            elapsed_ms = int((perf_counter() - started) * 1000)
            _console_attempt_log(attempt_id, "vector", f"vector search completed in {elapsed_ms}ms with {len(vector_examples)} result(s)")
        if vector_examples:
            return vector_examples, "vector"
    except Exception as exc:
        if attempt_id:
            _console_attempt_log(attempt_id, "vector", f"vector DB fallback reason: {type(exc).__name__}: {exc}")
        pass

    scored = [
        (_token_similarity(question, str(example.get("user_question") or "")), example)
        for example in examples
        if example.get("final_sql")
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "user_question": str(example.get("user_question") or ""),
            "sql": str(example.get("final_sql") or ""),
        }
        for score, example in scored[:limit]
        if score > 0
    ], "keyword"


def _is_gold_eligible(attempt: dict[str, Any], user_feedback_status: str, admin_approved: bool) -> bool:
    final_sql = str(attempt.get("final_sql") or "")
    execution_status = str(attempt.get("execution_status") or "").lower()
    execution_error = attempt.get("execution_error")
    if not admin_approved:
        return False
    if user_feedback_status.lower() != "correct":
        return False
    if execution_status != "success":
        return False
    if execution_error:
        return False
    if not final_sql:
        return False
    try:
        validate_select_sql(final_sql)
    except Exception:
        return False
    return True


def _token_similarity(left: str, right: str) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0
    overlap = left_tokens & right_tokens
    return len(overlap) / max(len(left_tokens | right_tokens), 1)


def _tokens(value: str) -> set[str]:
    stop_words = {"the", "and", "for", "with", "show", "give", "report", "list", "all"}
    return {
        token
        for token in re.findall(r"[a-z0-9_]+", value.lower())
        if len(token) > 2 and token not in stop_words
    }


def _row_to_dict(row: Any) -> dict[str, Any]:
    data = dict(row)
    for key in ("admin_approved", "is_gold_example"):
        data[key] = bool(data.get(key))
    return data


def _serialize_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return value


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _console_attempt_log(attempt_id: str, step: str, message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    sys.stderr.write(f"[ai-sql {timestamp} attempt={attempt_id} step={step}] {message}\n")
    sys.stderr.flush()
