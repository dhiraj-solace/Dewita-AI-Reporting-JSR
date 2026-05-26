from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from app.db import get_engine
from app.services.catalog import load_report_categories


DEFAULT_ROLES = ["Super Admin", "HR", "Project Manager", "Team Leader", "Team Member"]
DEFAULT_SCOPE = "none"
VALID_SCOPES = {"all", "role", "team", "project", "self", "none"}

DEFAULT_ROLE_CATEGORY_RULES: dict[str, dict[str, str]] = {
    "Super Admin": {
        "*": "all",
    },
    "HR": {
        "attendance": "all",
        "timesheet": "all",
        "team_employee": "all",
    },
    "Project Manager": {
        "project": "project",
        "task": "project",
        "timesheet": "project",
        "revision": "project",
        "quality": "project",
        "product": "project",
        "checklist": "project",
        "markup": "project",
    },
    "Team Leader": {
        "project": "team",
        "task": "team",
        "timesheet": "team",
        "revision": "team",
        "quality": "team",
        "team_employee": "team",
        "checklist": "team",
        "markup": "team",
    },
    "Team Member": {
        "attendance": "self",
        "timesheet": "self",
        "task": "self",
        "project": "self",
    },
}


class ReportPermissionError(Exception):
    pass


def ensure_role_report_permissions_table() -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS role_report_permissions (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        role_name VARCHAR(100) NOT NULL,
        report_category VARCHAR(100) NOT NULL,
        can_view BOOLEAN NOT NULL DEFAULT FALSE,
        can_create BOOLEAN NOT NULL DEFAULT FALSE,
        can_export BOOLEAN NOT NULL DEFAULT FALSE,
        can_save BOOLEAN NOT NULL DEFAULT FALSE,
        can_view_saved BOOLEAN NOT NULL DEFAULT FALSE,
        data_scope VARCHAR(50) NOT NULL DEFAULT 'self',
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        UNIQUE KEY uq_role_report_category (role_name, report_category)
    )
    """
    with get_engine().begin() as conn:
        conn.execute(text(ddl))
        _seed_default_permissions(conn)


def list_role_report_permissions() -> dict[str, Any]:
    ensure_role_report_permissions_table()
    categories = _category_ids()
    roles = _role_names()
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT role_name, report_category, can_view, can_create, can_export,
                       can_save, can_view_saved, data_scope
                FROM role_report_permissions
                ORDER BY role_name, report_category
                """
            )
        ).mappings().all()
    return {
        "roles": roles,
        "categories": load_report_categories().get("categories", []),
        "permissions": [_row_to_permission(dict(row)) for row in rows if row["report_category"] in categories],
        "scopes": ["all", "role", "team", "project", "self", "none"],
    }


def replace_role_report_permissions(permissions: list[dict[str, Any]]) -> dict[str, Any]:
    ensure_role_report_permissions_table()
    categories = _category_ids()
    now = _now()
    normalized = [_normalize_permission(item, categories, now) for item in permissions]
    with get_engine().begin() as conn:
        for item in normalized:
            conn.execute(
                text(
                    """
                    INSERT INTO role_report_permissions (
                        role_name, report_category, can_view, can_create, can_export,
                        can_save, can_view_saved, data_scope, created_at, updated_at
                    ) VALUES (
                        :role_name, :report_category, :can_view, :can_create, :can_export,
                        :can_save, :can_view_saved, :data_scope, :created_at, :updated_at
                    )
                    ON DUPLICATE KEY UPDATE
                        can_view = VALUES(can_view),
                        can_create = VALUES(can_create),
                        can_export = VALUES(can_export),
                        can_save = VALUES(can_save),
                        can_view_saved = VALUES(can_view_saved),
                        data_scope = VALUES(data_scope),
                        updated_at = VALUES(updated_at)
                    """
                ),
                item,
            )
    return list_role_report_permissions()


def get_role_permission(role_name: str | None, report_category: str) -> dict[str, Any] | None:
    ensure_role_report_permissions_table()
    role = _normalize_role_name(role_name)
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT role_name, report_category, can_view, can_create, can_export,
                       can_save, can_view_saved, data_scope
                FROM role_report_permissions
                WHERE role_name = :role_name AND report_category = :report_category
                """
            ),
            {"role_name": role, "report_category": report_category},
        ).mappings().first()
    return _row_to_permission(dict(row)) if row else None


def list_allowed_report_categories(role_name: str | None, action: str) -> list[str]:
    ensure_role_report_permissions_table()
    role = _normalize_role_name(role_name)
    field = f"can_{action}"
    allowed_fields = {"can_view", "can_create", "can_export", "can_save", "can_view_saved"}
    if field not in allowed_fields:
        raise ValueError(f"Unknown report permission action '{action}'.")
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT report_category
                FROM role_report_permissions
                WHERE role_name = :role_name
                  AND {field} = TRUE
                  AND data_scope <> 'none'
                """
            ),
            {"role_name": role},
        ).all()
    return [str(row[0]) for row in rows]


def assert_report_permission(role_name: str | None, report_category: str, action: str) -> dict[str, Any]:
    permission = get_role_permission(role_name, report_category)
    field = f"can_{action}"
    role = _normalize_role_name(role_name)
    if not permission or not bool(permission.get(field)):
        raise ReportPermissionError(
            f"{role} does not have permission to {action} {report_category} reports."
        )
    if permission.get("data_scope") == "none":
        raise ReportPermissionError(
            f"{role} has no data scope for {report_category} reports."
        )
    return permission


def _seed_default_permissions(conn: Any) -> None:
    existing = conn.execute(text("SELECT COUNT(*) FROM role_report_permissions")).scalar()
    if existing:
        return
    now = _now()
    categories = _category_ids()
    for role in DEFAULT_ROLES:
        rules = DEFAULT_ROLE_CATEGORY_RULES.get(role, {})
        for category in categories:
            scope = rules.get("*") or rules.get(category) or DEFAULT_SCOPE
            allowed = scope != "none"
            conn.execute(
                text(
                    """
                    INSERT INTO role_report_permissions (
                        role_name, report_category, can_view, can_create, can_export,
                        can_save, can_view_saved, data_scope, created_at, updated_at
                    ) VALUES (
                        :role_name, :report_category, :can_view, :can_create, :can_export,
                        :can_save, :can_view_saved, :data_scope, :created_at, :updated_at
                    )
                    """
                ),
                {
                    "role_name": role,
                    "report_category": category,
                    "can_view": allowed,
                    "can_create": allowed,
                    "can_export": allowed,
                    "can_save": allowed,
                    "can_view_saved": allowed,
                    "data_scope": scope,
                    "created_at": now,
                    "updated_at": now,
                },
            )


def _role_names() -> list[str]:
    roles = set(DEFAULT_ROLES)
    try:
        with get_engine().connect() as conn:
            rows = conn.execute(text("SELECT name FROM roles ORDER BY name")).all()
        roles.update(str(row[0]) for row in rows if row[0])
    except Exception:
        pass
    return sorted(roles, key=lambda value: (value != "Super Admin", value.lower()))


def _category_ids() -> set[str]:
    return {
        str(category.get("id"))
        for category in load_report_categories().get("categories", [])
        if category.get("id")
    }


def _normalize_permission(item: dict[str, Any], categories: set[str], now: datetime) -> dict[str, Any]:
    category = str(item.get("report_category") or "").strip()
    if category not in categories:
        raise ValueError(f"Unknown report category '{category}'.")
    scope = str(item.get("data_scope") or "self").strip().lower()
    if scope not in VALID_SCOPES:
        raise ValueError(f"Invalid data scope '{scope}'.")
    return {
        "role_name": _normalize_role_name(item.get("role_name")),
        "report_category": category,
        "can_view": bool(item.get("can_view")),
        "can_create": bool(item.get("can_create")),
        "can_export": bool(item.get("can_export")),
        "can_save": bool(item.get("can_save")),
        "can_view_saved": bool(item.get("can_view_saved")),
        "data_scope": scope,
        "created_at": now,
        "updated_at": now,
    }


def _normalize_role_name(role_name: Any) -> str:
    role = str(role_name or "Super Admin").strip()
    return role or "Super Admin"


def _row_to_permission(row: dict[str, Any]) -> dict[str, Any]:
    for key in ("can_view", "can_create", "can_export", "can_save", "can_view_saved"):
        row[key] = bool(row.get(key))
    return row


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
