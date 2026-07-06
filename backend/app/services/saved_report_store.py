import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import bindparam, text

from app.db import get_engine
from app.models import GeneratedReport
from app.services.audit_log import create_audit_log
from app.services.report_permissions import list_allowed_report_categories
from app.services.saved_report_shares import list_shared_report_rows
from app.services.users import ensure_users_table


SAVED_REPORT_FIELDS = (
    "id",
    "attempt_id",
    "report_category",
    "report_variant",
    "presentation_json",
    "created_by_role",
    "created_by_user_id",
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
    ensure_users_table()
    ddl = """
    CREATE TABLE IF NOT EXISTS saved_reports (
        id VARCHAR(36) PRIMARY KEY,
        attempt_id VARCHAR(36) NULL,
        report_category VARCHAR(100) NULL,
        report_variant VARCHAR(100) NULL,
        presentation_json LONGTEXT NULL,
        created_by_role VARCHAR(100) NULL,
        created_by_user_id VARCHAR(36) NULL,
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
        _ensure_saved_report_columns(conn)


def _ensure_saved_report_columns(conn: Any) -> None:
    columns = {
        "report_category": "VARCHAR(100) NULL AFTER attempt_id",
        "report_variant": "VARCHAR(100) NULL AFTER report_category",
        "presentation_json": "LONGTEXT NULL AFTER report_variant",
        "created_by_role": "VARCHAR(100) NULL AFTER presentation_json",
        "created_by_user_id": "VARCHAR(36) NULL AFTER created_by_role",
    }
    for name, definition in columns.items():
        exists = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'saved_reports'
                  AND COLUMN_NAME = :name
                """
            ),
            {"name": name},
        ).scalar()
        if not exists:
            conn.execute(text(f"ALTER TABLE saved_reports ADD COLUMN {name} {definition}"))


def save_generated_report(report: GeneratedReport) -> str:
    ensure_saved_reports_table()
    report_category = report.report_category or "custom"
    created_by_role = report.created_by_role or "Super Admin"
    created_by_user_id = report.created_by_user_id
    existing_id = find_existing_saved_report(report.question, report.sql)
    if existing_id:
        with get_engine().begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE saved_reports
                    SET report_category = COALESCE(report_category, :report_category),
                        report_variant = :report_variant,
                        presentation_json = :presentation_json,
                        created_by_role = COALESCE(created_by_role, :created_by_role),
                        created_by_user_id = COALESCE(created_by_user_id, :created_by_user_id),
                        updated_at = :updated_at
                    WHERE id = :id
                    """
                ),
                {
                    "id": existing_id,
                    "report_category": report_category,
                    "report_variant": report.report_variant,
                    "presentation_json": _json(report.presentation),
                    "created_by_role": created_by_role,
                    "created_by_user_id": created_by_user_id,
                    "updated_at": _now(),
                },
            )
        create_audit_log(
            event_type="saved_report_reused",
            actor_role=created_by_role,
            report_id=existing_id,
            report_category=report_category,
            action="save",
            metadata={"question": report.question, "row_count": report.row_count},
        )
        return existing_id
    report_id = report.saved_report_id or str(uuid4())
    now = _now()
    payload = {
        "id": report_id,
        "attempt_id": report.attempt_id,
        "report_category": report_category,
        "report_variant": report.report_variant,
        "presentation_json": _json(report.presentation),
        "created_by_role": created_by_role,
        "created_by_user_id": created_by_user_id,
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
                    id, attempt_id, report_category, report_variant, presentation_json,
                    created_by_role, created_by_user_id, title, question, sql_text, explanation, assumptions,
                    columns_json, rows_json, row_count, dry_run, warnings, retry_attempts,
                    created_at, updated_at
                ) VALUES (
                    :id, :attempt_id, :report_category, :report_variant, :presentation_json,
                    :created_by_role, :created_by_user_id, :title, :question, :sql_text, :explanation, :assumptions,
                    :columns_json, :rows_json, :row_count, :dry_run, :warnings, :retry_attempts,
                    :created_at, :updated_at
                )
                """
            ),
            payload,
        )
    create_audit_log(
        event_type="saved_report_created",
        actor_role=created_by_role,
        report_id=report_id,
        report_category=report_category,
        action="save",
        after={
            "title": report.title,
            "question": report.question,
            "row_count": report.row_count,
            "dry_run": report.dry_run,
        },
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


def list_saved_reports(
    limit: int = 50,
    role_name: str | None = None,
    user_id: str | None = None,
    include_shared: bool = True,
) -> list[dict[str, Any]]:
    ensure_saved_reports_table()
    allowed_categories = list_allowed_report_categories(role_name, "view_saved")
    if not allowed_categories:
        reports: list[dict[str, Any]] = []
    else:
        with get_engine().connect() as conn:
            stmt = text(
                    """
                    SELECT r.id, r.title, r.question, COALESCE(r.report_category, 'custom') AS report_category,
                           r.created_by_role, r.created_by_user_id, creator.name AS created_by_name,
                           NULL AS shared_by_name, 'Created by me' AS shared_label,
                           FALSE AS is_shared, FALSE AS is_new, FALSE AS can_export_shared,
                           r.row_count, r.created_at
                    FROM saved_reports r
                    LEFT JOIN users creator ON creator.id = r.created_by_user_id
                    WHERE COALESCE(r.report_category, 'custom') IN :allowed_categories
                      AND (:user_id IS NULL OR r.created_by_user_id = :user_id OR :is_super_admin = TRUE)
                    ORDER BY r.created_at DESC
                    LIMIT :limit
                    """
                ).bindparams(bindparam("allowed_categories", expanding=True))
            rows = conn.execute(
                stmt,
                {
                    "limit": limit,
                    "allowed_categories": tuple(allowed_categories),
                    "user_id": user_id,
                    "is_super_admin": (role_name or "").strip().lower() == "super admin",
                },
            ).mappings().all()
        reports = [dict(row) for row in rows]
    if include_shared and user_id:
        seen = {str(row["id"]) for row in reports}
        for row in list_shared_report_rows(user_id, limit):
            if str(row["id"]) not in seen:
                reports.append(row)
                seen.add(str(row["id"]))
    reports.sort(key=lambda row: row.get("created_at"), reverse=True)
    return reports[:limit]


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
        report_category=row.get("report_category") or "custom",
        report_variant=row.get("report_variant"),
        presentation=_loads(row.get("presentation_json"), {}),
        created_by_role=row.get("created_by_role"),
        created_by_user_id=row.get("created_by_user_id"),
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
