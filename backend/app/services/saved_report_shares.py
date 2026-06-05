from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from app.db import get_engine
from app.services.audit_log import create_audit_log
from app.services.users import get_user, get_user_by_email


def ensure_saved_report_shares_table() -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS saved_report_shares (
        id VARCHAR(36) PRIMARY KEY,
        report_id VARCHAR(36) NOT NULL,
        shared_by_user_id VARCHAR(36) NULL,
        shared_by_role VARCHAR(100) NULL,
        shared_with_user_id VARCHAR(36) NOT NULL,
        message TEXT NULL,
        can_view BOOLEAN NOT NULL DEFAULT TRUE,
        can_export BOOLEAN NOT NULL DEFAULT FALSE,
        viewed_at DATETIME NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        UNIQUE KEY uq_report_shared_user (report_id, shared_with_user_id),
        INDEX idx_saved_report_shares_report_id (report_id),
        INDEX idx_saved_report_shares_user_id (shared_with_user_id),
        INDEX idx_saved_report_shares_created_at (created_at)
    )
    """
    with get_engine().begin() as conn:
        conn.execute(text(ddl))


def share_saved_report_with_user(
    *,
    report_id: str,
    recipient_user_id: str | None = None,
    recipient_email: str | None = None,
    actor: dict[str, Any] | None = None,
    actor_role: str | None = None,
    message: str | None = None,
    can_export: bool = False,
    report_category: str | None = None,
) -> dict[str, Any]:
    ensure_saved_report_shares_table()
    recipient = get_user(recipient_user_id) if recipient_user_id else get_user_by_email(recipient_email)
    if not recipient:
        raise ValueError("Select an existing active user to share this report with.")
    if not recipient.get("is_active"):
        raise ValueError("Cannot share reports with an inactive user.")
    actor_user_id = actor.get("id") if actor else None
    if actor_user_id and actor_user_id == recipient["id"]:
        raise ValueError("A report is already available to the user who shared it.")
    now = _now()
    share_id = str(uuid4())
    payload = {
        "id": share_id,
        "report_id": report_id,
        "shared_by_user_id": actor_user_id,
        "shared_by_role": actor.get("role_name") if actor else actor_role,
        "shared_with_user_id": recipient["id"],
        "message": message,
        "can_view": True,
        "can_export": bool(can_export),
        "viewed_at": None,
        "created_at": now,
        "updated_at": now,
    }
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO saved_report_shares (
                    id, report_id, shared_by_user_id, shared_by_role, shared_with_user_id,
                    message, can_view, can_export, viewed_at, created_at, updated_at
                ) VALUES (
                    :id, :report_id, :shared_by_user_id, :shared_by_role, :shared_with_user_id,
                    :message, :can_view, :can_export, :viewed_at, :created_at, :updated_at
                )
                ON DUPLICATE KEY UPDATE
                    shared_by_user_id = VALUES(shared_by_user_id),
                    shared_by_role = VALUES(shared_by_role),
                    message = VALUES(message),
                    can_view = VALUES(can_view),
                    can_export = VALUES(can_export),
                    updated_at = VALUES(updated_at)
                """
            ),
            payload,
        )
    create_audit_log(
        event_type="report_shared_in_app",
        actor_role=payload["shared_by_role"],
        target_role=recipient.get("role_name"),
        report_id=report_id,
        report_category=report_category,
        action="share",
        metadata={
            "recipient_user_id": recipient["id"],
            "recipient_email": recipient["email"],
            "can_export": bool(can_export),
        },
    )
    row = get_report_share(report_id, recipient["id"])
    return row or payload


def get_report_share(report_id: str, user_id: str | None) -> dict[str, Any] | None:
    if not user_id:
        return None
    ensure_saved_report_shares_table()
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT s.*, sharer.name AS shared_by_name, recipient.name AS shared_with_name
                FROM saved_report_shares s
                LEFT JOIN users sharer ON sharer.id = s.shared_by_user_id
                LEFT JOIN users recipient ON recipient.id = s.shared_with_user_id
                WHERE s.report_id = :report_id
                  AND s.shared_with_user_id = :user_id
                  AND s.can_view = TRUE
                """
            ),
            {"report_id": report_id, "user_id": user_id},
        ).mappings().first()
    return dict(row) if row else None


def mark_report_share_viewed(report_id: str, user_id: str | None) -> None:
    if not user_id:
        return
    ensure_saved_report_shares_table()
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                UPDATE saved_report_shares
                SET viewed_at = COALESCE(viewed_at, :viewed_at), updated_at = :updated_at
                WHERE report_id = :report_id
                  AND shared_with_user_id = :user_id
                  AND can_view = TRUE
                """
            ),
            {"report_id": report_id, "user_id": user_id, "viewed_at": _now(), "updated_at": _now()},
        )


def list_shared_report_rows(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    ensure_saved_report_shares_table()
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT r.id, r.title, r.question, COALESCE(r.report_category, 'custom') AS report_category,
                       r.created_by_role, r.created_by_user_id, creator.name AS created_by_name,
                       sharer.name AS shared_by_name, r.row_count, r.created_at,
                       TRUE AS is_shared, s.viewed_at IS NULL AS is_new, s.can_export AS can_export_shared,
                       CASE WHEN s.viewed_at IS NULL THEN 'New' ELSE 'Shared' END AS shared_label
                FROM saved_report_shares s
                JOIN saved_reports r ON r.id = s.report_id
                LEFT JOIN users creator ON creator.id = r.created_by_user_id
                LEFT JOIN users sharer ON sharer.id = s.shared_by_user_id
                WHERE s.shared_with_user_id = :user_id
                  AND s.can_view = TRUE
                ORDER BY s.created_at DESC
                LIMIT :limit
                """
            ),
            {"user_id": user_id, "limit": limit},
        ).mappings().all()
    return [dict(row) for row in rows]


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
