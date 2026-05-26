import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from app.db import get_engine
from app.models import GeneratedReport


SAVED_REPORT_FIELDS = (
    "id",
    "attempt_id",
    "title",
    "question",
    "sql",
    "explanation",
    "assumptions",
    "columns_json",
    "rows_json",
    "row_count",
    "dry_run",
    "warnings",
    "retry_attempts",
    "created_at",
    "updated_at",
)


def ensure_saved_reports_table() -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS saved_reports (
        id VARCHAR(36) PRIMARY KEY,
        attempt_id VARCHAR(36) NULL,
        title TEXT NOT NULL,
        question TEXT NOT NULL,
        sql_text LONGTEXT NOT NULL,
        explanation LONGTEXT NULL,
        assumptions LONGTEXT NULL,
        columns_json LONGTEXT NOT NULL,
        rows_json LONGTEXT NOT NULL,
        row_count INT NOT NULL,
        dry_run BOOLEAN NOT NULL DEFAULT FALSE,
        warnings LONGTEXT NULL,
        retry_attempts LONGTEXT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        INDEX idx_saved_reports_created_at (created_at),
        INDEX idx_saved_reports_attempt_id (attempt_id)
    )
    """
    with get_engine().begin() as conn:
        conn.execute(text(ddl))


def save_generated_report(report: GeneratedReport) -> str:
    ensure_saved_reports_table()
    existing_id = find_existing_saved_report(report.question, report.sql)
    if existing_id:
        return existing_id
    report_id = report.saved_report_id or str(uuid4())
    now = _now()
    payload = {
        "id": report_id,
        "attempt_id": report.attempt_id,
        "title": report.title,
        "question": report.question,
        "sql_text": report.sql,
        "explanation": report.explanation,
        "assumptions": _json(report.assumptions),
        "columns_json": _json(report.columns),
        "rows_json": _json(report.rows),
        "row_count": report.row_count,
        "dry_run": report.dry_run,
        "warnings": _json(report.warnings),
        "retry_attempts": _json([attempt.model_dump() for attempt in report.retry_attempts]),
        "created_at": now,
        "updated_at": now,
    }
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO saved_reports (
                    id, attempt_id, title, question, sql_text, explanation, assumptions,
                    columns_json, rows_json, row_count, dry_run, warnings, retry_attempts,
                    created_at, updated_at
                ) VALUES (
                    :id, :attempt_id, :title, :question, :sql_text, :explanation, :assumptions,
                    :columns_json, :rows_json, :row_count, :dry_run, :warnings, :retry_attempts,
                    :created_at, :updated_at
                )
                """
            ),
            payload,
        )
    return report_id


def find_existing_saved_report(question: str, sql: str) -> str | None:
    ensure_saved_reports_table()
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT id
                FROM saved_reports
                WHERE question = :question AND sql_text = :sql_text
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"question": question, "sql_text": sql},
        ).mappings().first()
    return str(row["id"]) if row else None


def list_saved_reports(limit: int = 50) -> list[dict[str, Any]]:
    ensure_saved_reports_table()
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, title, question, row_count, created_at
                FROM saved_reports
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()
    return [dict(row) for row in rows]


def get_saved_report(report_id: str) -> GeneratedReport | None:
    ensure_saved_reports_table()
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT * FROM saved_reports WHERE id = :id"),
            {"id": report_id},
        ).mappings().first()
    if not row:
        return None
    return _row_to_report(dict(row))


def _row_to_report(row: dict[str, Any]) -> GeneratedReport:
    return GeneratedReport(
        saved_report_id=row["id"],
        attempt_id=row.get("attempt_id"),
        title=row["title"],
        question=row["question"],
        sql=row["sql_text"],
        explanation=row.get("explanation") or "",
        assumptions=_loads(row.get("assumptions"), []),
        columns=_loads(row.get("columns_json"), []),
        rows=_loads(row.get("rows_json"), []),
        row_count=int(row.get("row_count") or 0),
        dry_run=bool(row.get("dry_run")),
        warnings=_loads(row.get("warnings"), []),
        retry_attempts=_loads(row.get("retry_attempts"), []),
    )


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=_json_default)


def _loads(value: Any, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
