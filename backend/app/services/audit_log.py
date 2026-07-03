import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from app.db import get_engine


def ensure_audit_log_table() -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS report_audit_logs (
        id VARCHAR(36) PRIMARY KEY,
        event_type VARCHAR(100) NOT NULL,
        actor_role VARCHAR(100) NULL,
        target_role VARCHAR(100) NULL,
        report_id VARCHAR(36) NULL,
        report_category VARCHAR(100) NULL,
        action VARCHAR(100) NULL,
        before_json LONGTEXT NULL,
        after_json LONGTEXT NULL,
        metadata_json LONGTEXT NULL,
        created_at DATETIME NOT NULL,
        INDEX idx_report_audit_created_at (created_at),
        INDEX idx_report_audit_event_type (event_type),
        INDEX idx_report_audit_report_id (report_id),
        INDEX idx_report_audit_actor_role (actor_role)
    )
    """
    with get_engine().begin() as conn:
        conn.execute(text(ddl))


def create_audit_log(
    *,
    event_type: str,
    actor_role: str | None = None,
    target_role: str | None = None,
    report_id: str | None = None,
    report_category: str | None = None,
    action: str | None = None,
    before: Any = None,
    after: Any = None,
    metadata: Any = None,
) -> str:
    ensure_audit_log_table()
    log_id = str(uuid4())
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO report_audit_logs (
                    id, event_type, actor_role, target_role, report_id, report_category,
                    action, before_json, after_json, metadata_json, created_at
                ) VALUES (
                    :id, :event_type, :actor_role, :target_role, :report_id, :report_category,
                    :action, :before_json, :after_json, :metadata_json, :created_at
                )
                """
            ),
            {
                "id": log_id,
                "event_type": event_type,
                "actor_role": actor_role,
                "target_role": target_role,
                "report_id": report_id,
                "report_category": report_category,
                "action": action,
                "before_json": _json_or_none(before),
                "after_json": _json_or_none(after),
                "metadata_json": _json_or_none(metadata),
                "created_at": _now(),
            },
        )
    return log_id


def list_audit_logs(limit: int = 100) -> list[dict[str, Any]]:
    ensure_audit_log_table()
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, event_type, actor_role, target_role, report_id, report_category,
                       action, before_json, after_json, metadata_json, created_at
                FROM report_audit_logs
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()
    return [dict(row) for row in rows]


def _json_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
