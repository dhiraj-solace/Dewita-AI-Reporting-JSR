import re
import sys
import hashlib
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
    "wrong_ordering",
    "wrong_date_range",
    "unsafe_query",
    "limit_mismatch",
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
        use_in_context BOOLEAN NOT NULL DEFAULT TRUE,
        validation_stage VARCHAR(50) NOT NULL DEFAULT 'backend',
        validator_source VARCHAR(50) NOT NULL DEFAULT 'backend',
        missing_table VARCHAR(255) NULL,
        missing_column VARCHAR(255) NULL,
        fix_hint LONGTEXT NULL,
        mistake_fingerprint VARCHAR(64) NULL,
        generated_output_number INT NULL,
        retry_number INT NULL,
        created_at DATETIME NOT NULL
    )
    """
    with get_engine().begin() as conn:
        conn.execute(text(ddl))
        _ensure_mistake_columns(conn)


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
    validation_stage: str = "backend",
    validator_source: str = "backend",
    missing_table: str | None = None,
    missing_column: str | None = None,
    fix_hint: str | None = None,
    generated_output_number: int | None = None,
    retry_number: int | None = None,
    use_in_context: bool | None = None,
) -> str:
    ensure_sql_mistake_examples_table()
    normalized_type = mistake_type if mistake_type in MISTAKE_TYPES else "unknown"
    fingerprint = _mistake_fingerprint(
        query_attempt_id,
        wrong_sql,
        validation_reason or validator_feedback,
        validation_stage,
        validator_source,
    )
    with get_engine().connect() as conn:
        existing = conn.execute(
            text(
                """
                SELECT id
                FROM sql_mistake_examples
                WHERE mistake_fingerprint = :mistake_fingerprint
                LIMIT 1
                """
            ),
            {"mistake_fingerprint": fingerprint},
        ).mappings().first()
    if existing:
        _console_log("MISTAKE_EXAMPLE_DEDUPED", {"attemptId": query_attempt_id, "mistakeType": normalized_type})
        return str(existing["id"])
    mistake_id = str(uuid4())
    include_context = validator_source != "judge_llm" if use_in_context is None else bool(use_in_context)
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO sql_mistake_examples (
                    id, query_attempt_id, user_question, wrong_sql, validator_feedback,
                    validation_reason, mistake_type, corrected_sql, final_correct_sql,
                    risk_level, use_in_context, validation_stage, validator_source,
                    missing_table, missing_column, fix_hint, mistake_fingerprint,
                    generated_output_number, retry_number, created_at
                ) VALUES (
                    :id, :query_attempt_id, :user_question, :wrong_sql, :validator_feedback,
                    :validation_reason, :mistake_type, :corrected_sql, :final_correct_sql,
                    :risk_level, :use_in_context, :validation_stage, :validator_source,
                    :missing_table, :missing_column, :fix_hint, :mistake_fingerprint,
                    :generated_output_number, :retry_number, :created_at
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
                "use_in_context": include_context,
                "validation_stage": validation_stage,
                "validator_source": validator_source,
                "missing_table": missing_table,
                "missing_column": missing_column,
                "fix_hint": fix_hint or corrected_sql,
                "mistake_fingerprint": fingerprint,
                "generated_output_number": generated_output_number,
                "retry_number": retry_number,
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


def list_mistake_groups(limit: int = 100, examples_per_group: int = 5) -> list[dict[str, Any]]:
    mistakes = list_mistake_examples(limit * 5)
    groups: dict[str, dict[str, Any]] = {}
    for mistake in mistakes:
        reason = str(mistake.get("validation_reason") or mistake.get("validator_feedback") or "").strip()
        group_key = _mistake_group_key(
            str(mistake.get("user_question") or ""),
            str(mistake.get("mistake_type") or "unknown"),
            reason,
        )
        group = groups.setdefault(
            group_key,
            {
                "group_key": group_key,
                "user_question": str(mistake.get("user_question") or ""),
                "mistake_type": str(mistake.get("mistake_type") or "unknown"),
                "reason": reason,
                "risk_level": str(mistake.get("risk_level") or "medium"),
                "occurrence_count": 0,
                "included_count": 0,
                "latest_created_at": mistake.get("created_at"),
                "examples": [],
            },
        )
        group["occurrence_count"] += 1
        if bool(mistake.get("use_in_context", True)):
            group["included_count"] += 1
        if _is_newer(mistake.get("created_at"), group.get("latest_created_at")):
            group["latest_created_at"] = mistake.get("created_at")
        if len(group["examples"]) < examples_per_group:
            group["examples"].append(mistake)
    grouped = list(groups.values())
    grouped.sort(key=lambda item: (int(item["occurrence_count"]), item.get("latest_created_at")), reverse=True)
    return grouped[:limit]


def set_mistake_context_usage(mistake_id: str, use_in_context: bool) -> dict[str, Any]:
    ensure_sql_mistake_examples_table()
    with get_engine().begin() as conn:
        result = conn.execute(
            text(
                """
                UPDATE sql_mistake_examples
                SET use_in_context = :use_in_context
                WHERE id = :id
                """
            ),
            {"id": mistake_id, "use_in_context": bool(use_in_context)},
        )
        if result.rowcount == 0:
            raise ValueError("SQL mistake example was not found.")
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT * FROM sql_mistake_examples WHERE id = :id"),
            {"id": mistake_id},
        ).mappings().first()
    if not row:
        raise ValueError("SQL mistake example was not found.")
    return dict(row)


def set_mistake_group_context_usage(group_key: str, use_in_context: bool) -> dict[str, Any]:
    ensure_sql_mistake_examples_table()
    mistakes = list_mistake_examples(1000)
    ids = [
        str(mistake["id"])
        for mistake in mistakes
        if _mistake_group_key(
            str(mistake.get("user_question") or ""),
            str(mistake.get("mistake_type") or "unknown"),
            str(mistake.get("validation_reason") or mistake.get("validator_feedback") or "").strip(),
        ) == group_key
    ]
    if not ids:
        raise ValueError("SQL mistake group was not found.")
    with get_engine().begin() as conn:
        for mistake_id in ids:
            conn.execute(
                text(
                    """
                    UPDATE sql_mistake_examples
                    SET use_in_context = :use_in_context
                    WHERE id = :id
                    """
                ),
                {"id": mistake_id, "use_in_context": bool(use_in_context)},
            )
    groups = [group for group in list_mistake_groups(200) if group["group_key"] == group_key]
    if not groups:
        raise ValueError("SQL mistake group was not found.")
    return groups[0]


def similar_mistake_examples(question: str, limit: int = 3) -> list[dict[str, str]]:
    mistakes = [
        mistake for mistake in list_mistake_examples(200)
        if bool(mistake.get("use_in_context", True))
    ]
    mistakes = [
        mistake for mistake in mistakes
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


def _mistake_group_key(question: str, mistake_type: str, reason: str) -> str:
    normalized = "|".join([
        " ".join(sorted(_tokens(question))),
        mistake_type.strip().lower(),
        _normalize_reason(reason),
    ])
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def _normalize_reason(reason: str) -> str:
    value = re.sub(r"\s+", " ", reason.lower()).strip()
    value = re.sub(r"`[^`]+`", "`field`", value)
    value = re.sub(r"\b[a-f0-9-]{8,}\b", "id", value)
    return value[:240]


def _is_newer(left: Any, right: Any) -> bool:
    if right is None:
        return True
    if left is None:
        return False
    return left > right


def _ensure_mistake_columns(conn: Any) -> None:
    columns = {
        "use_in_context": "BOOLEAN NOT NULL DEFAULT TRUE AFTER risk_level",
        "validation_stage": "VARCHAR(50) NOT NULL DEFAULT 'backend' AFTER use_in_context",
        "validator_source": "VARCHAR(50) NOT NULL DEFAULT 'backend' AFTER validation_stage",
        "missing_table": "VARCHAR(255) NULL AFTER validator_source",
        "missing_column": "VARCHAR(255) NULL AFTER missing_table",
        "fix_hint": "LONGTEXT NULL AFTER missing_column",
        "mistake_fingerprint": "VARCHAR(64) NULL AFTER fix_hint",
        "generated_output_number": "INT NULL AFTER mistake_fingerprint",
        "retry_number": "INT NULL AFTER generated_output_number",
    }
    for name, definition in columns.items():
        exists = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'sql_mistake_examples'
                  AND COLUMN_NAME = :name
                """
            ),
            {"name": name},
        ).scalar()
        if not exists:
            conn.execute(text(f"ALTER TABLE sql_mistake_examples ADD COLUMN {name} {definition}"))


def _mistake_fingerprint(
    query_attempt_id: str,
    wrong_sql: str | None,
    reason: str,
    validation_stage: str,
    validator_source: str,
) -> str:
    normalized = "|".join([
        query_attempt_id.strip().lower(),
        re.sub(r"\s+", " ", str(wrong_sql or "").strip().lower()),
        re.sub(r"\s+", " ", reason.strip().lower()),
        validation_stage.strip().lower(),
        validator_source.strip().lower(),
    ])
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _console_log(event: str, payload: dict[str, Any]) -> None:
    rendered = ", ".join(f"{key}={value}" for key, value in payload.items())
    sys.stderr.write(f"[AI-SQL][{event}] {rendered}\n")
    sys.stderr.flush()
