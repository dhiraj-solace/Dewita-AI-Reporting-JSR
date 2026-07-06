import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from app.core.config import get_settings
from app.db import get_engine
from app.services.audit_log import create_audit_log
from app.services.report_permissions import DEFAULT_ROLES


DIRECT_ADMIN_ID = "direct-super-admin"


def ensure_users_table() -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS users (
        id VARCHAR(36) PRIMARY KEY,
        name VARCHAR(150) NOT NULL,
        email VARCHAR(255) NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        role_name VARCHAR(100) NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_by_user_id VARCHAR(36) NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        UNIQUE KEY uq_users_email (email),
        INDEX idx_users_role_name (role_name),
        INDEX idx_users_is_active (is_active)
    )
    """
    with get_engine().begin() as conn:
        conn.execute(text(ddl))
        _ensure_user_columns(conn)
        _seed_default_admin(conn)


def list_users() -> list[dict[str, Any]]:
    ensure_users_table()
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, name, email, COALESCE(role_name, 'Team Member') AS role_name,
                       is_active, created_at, updated_at
                FROM users
                WHERE password_hash IS NOT NULL
                  AND password_hash <> ''
                ORDER BY is_active DESC, COALESCE(role_name, 'Team Member'), name, email
                """
            )
        ).mappings().all()
    return [_public_user(dict(row)) for row in rows]


def create_user(payload: dict[str, Any], actor: dict[str, Any] | None = None) -> dict[str, Any]:
    ensure_users_table()
    email = _normalize_email(payload.get("email"))
    role = _normalize_role(payload.get("role_name"))
    user_id = str(uuid4())
    uses_auto_id = _users_id_is_auto_increment()
    now = _now()
    row = {
        "id": user_id,
        "name": str(payload.get("name") or "").strip(),
        "email": email,
        "password_hash": _hash_password(str(payload.get("password") or "")),
        "role_name": role,
        "is_active": bool(payload.get("is_active", True)),
        "created_by_user_id": actor.get("id") if actor else None,
        "created_at": now,
        "updated_at": now,
    }
    if not row["name"]:
        raise ValueError("User name is required.")
    with get_engine().begin() as conn:
        existing = conn.execute(
            text("SELECT id, password_hash FROM users WHERE email = :email LIMIT 1"),
            {"email": email},
        ).mappings().first()
        if existing and existing.get("password_hash"):
            raise ValueError("A reporting user with this email already exists.")
        if existing:
            conn.execute(
                text(
                    """
                    UPDATE users
                    SET name = :name,
                        password_hash = :password_hash,
                        role_name = :role_name,
                        is_active = :is_active,
                        created_by_user_id = :created_by_user_id,
                        updated_at = :updated_at
                    WHERE id = :id
                    """
                ),
                {**row, "id": existing["id"]},
            )
            user_id = str(existing["id"])
        else:
            try:
                if uses_auto_id:
                    conn.execute(
                        text(
                            """
                            INSERT INTO users (
                                name, email, password_hash, role_name, is_active,
                                created_by_user_id, created_at, updated_at
                            ) VALUES (
                                :name, :email, :password_hash, :role_name, :is_active,
                                :created_by_user_id, :created_at, :updated_at
                            )
                            """
                        ),
                        row,
                    )
                else:
                    conn.execute(
                        text(
                            """
                            INSERT INTO users (
                                id, name, email, password_hash, role_name, is_active,
                                created_by_user_id, created_at, updated_at
                            ) VALUES (
                                :id, :name, :email, :password_hash, :role_name, :is_active,
                                :created_by_user_id, :created_at, :updated_at
                            )
                            """
                        ),
                        row,
                    )
            except Exception as exc:
                raise ValueError("A user with this email already exists.") from exc
    created = get_user_by_email(email)
    user_id = str(created["id"]) if created else user_id
    create_audit_log(
        event_type="user_created",
        actor_role=actor.get("role_name") if actor else None,
        target_role=role,
        action="create_user",
        after={"id": user_id, "name": row["name"], "email": email, "role_name": role},
    )
    return created or get_user(user_id) or _public_user(row)


def update_user(user_id: str, payload: dict[str, Any], actor: dict[str, Any] | None = None) -> dict[str, Any]:
    ensure_users_table()
    before = get_user(user_id)
    if before is None:
        raise ValueError("User was not found.")
    updates: dict[str, Any] = {"id": user_id, "updated_at": _now()}
    assignments = ["updated_at = :updated_at"]
    if payload.get("name") is not None:
        updates["name"] = str(payload.get("name") or "").strip()
        if not updates["name"]:
            raise ValueError("User name is required.")
        assignments.append("name = :name")
    if payload.get("email") is not None:
        updates["email"] = _normalize_email(payload.get("email"))
        assignments.append("email = :email")
    if payload.get("role_name") is not None:
        updates["role_name"] = _normalize_role(payload.get("role_name"))
        assignments.append("role_name = :role_name")
    if payload.get("is_active") is not None:
        updates["is_active"] = bool(payload.get("is_active"))
        assignments.append("is_active = :is_active")
    if payload.get("password"):
        updates["password_hash"] = _hash_password(str(payload.get("password")))
        assignments.append("password_hash = :password_hash")
    with get_engine().begin() as conn:
        conn.execute(text(f"UPDATE users SET {', '.join(assignments)} WHERE id = :id"), updates)
    after = get_user(user_id)
    create_audit_log(
        event_type="user_updated",
        actor_role=actor.get("role_name") if actor else None,
        target_role=after.get("role_name") if after else None,
        action="update_user",
        before=before,
        after=after,
    )
    return after or before


def authenticate_user(email: str, password: str) -> dict[str, Any] | None:
    direct_admin = _configured_direct_admin()
    if direct_admin and hmac.compare_digest(_normalize_email(email), direct_admin["email"]):
        if not hmac.compare_digest(password, get_settings().direct_admin_password or ""):
            return None
        return direct_admin

    ensure_users_table()
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT *
                FROM users
                WHERE email = :email
                  AND password_hash IS NOT NULL
                  AND password_hash <> ''
                LIMIT 1
                """
            ),
            {"email": _normalize_email(email)},
        ).mappings().first()
    if not row or not bool(row["is_active"]):
        return None
    user = dict(row)
    if not _verify_password(password, str(user["password_hash"])):
        return None
    create_audit_log(
        event_type="user_login",
        actor_role=user.get("role_name"),
        action="login",
        metadata={"user_id": user["id"], "email": user["email"]},
    )
    return _public_user(user)


def create_auth_token(user: dict[str, Any]) -> str:
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(minutes=max(5, settings.auth_token_ttl_minutes))
    payload = {
        "sub": user["id"],
        "email": user["email"],
        "role_name": user["role_name"],
        "exp": int(expires_at.timestamp()),
    }
    payload_raw = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _sign(payload_raw)
    return f"{payload_raw}.{signature}"


def get_user_from_token(token: str | None) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    payload_raw, signature = token.split(".", 1)
    if not hmac.compare_digest(_sign(payload_raw), signature):
        return None
    try:
        payload = json.loads(_unb64(payload_raw).decode("utf-8"))
    except Exception:
        return None
    if int(payload.get("exp") or 0) < int(datetime.now(UTC).timestamp()):
        return None
    direct_admin = _configured_direct_admin()
    if (
        direct_admin
        and hmac.compare_digest(str(payload.get("sub") or ""), direct_admin["id"])
        and hmac.compare_digest(
            _normalize_email(payload.get("email")),
            direct_admin["email"],
        )
    ):
        return direct_admin
    user = get_user(str(payload.get("sub") or ""))
    if not user or not user.get("is_active"):
        return None
    return user


def get_user(user_id: str) -> dict[str, Any] | None:
    ensure_users_table()
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, name, email, COALESCE(role_name, 'Team Member') AS role_name,
                       is_active, created_at, updated_at
                FROM users
                WHERE id = :id
                  AND password_hash IS NOT NULL
                  AND password_hash <> ''
                LIMIT 1
                """
            ),
            {"id": user_id},
        ).mappings().first()
    return _public_user(dict(row)) if row else None


def get_user_by_email(email: str | None) -> dict[str, Any] | None:
    if not email:
        return None
    ensure_users_table()
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, name, email, COALESCE(role_name, 'Team Member') AS role_name,
                       is_active, created_at, updated_at
                FROM users
                WHERE email = :email
                  AND password_hash IS NOT NULL
                  AND password_hash <> ''
                LIMIT 1
                """
            ),
            {"email": _normalize_email(email)},
        ).mappings().first()
    return _public_user(dict(row)) if row else None


def require_super_admin_user(user: dict[str, Any] | None) -> None:
    if not user or str(user.get("role_name") or "").strip().lower() != "super admin":
        raise PermissionError("Only Super Admin can manage users.")


def _configured_direct_admin() -> dict[str, Any] | None:
    settings = get_settings()
    email = str(settings.direct_admin_email or "").strip().lower()
    password = settings.direct_admin_password or ""
    if not settings.direct_admin_enabled or not email or not password or "@" not in email:
        return None
    return {
        "id": DIRECT_ADMIN_ID,
        "name": "Super Admin",
        "email": email,
        "role_name": "Super Admin",
        "is_active": True,
        "created_at": None,
        "updated_at": None,
    }


def _seed_default_admin(conn: Any) -> None:
    existing = conn.execute(
        text("SELECT id FROM users WHERE email = :email LIMIT 1"),
        {"email": "admin@devita.local"},
    ).mappings().first()
    password_hash = _hash_password("Admin@12345")
    now = _now()
    if existing:
        conn.execute(
            text(
                """
                UPDATE users
                SET name = :name,
                    password_hash = :password_hash,
                    role_name = :role_name,
                    is_active = TRUE,
                    updated_at = COALESCE(updated_at, :updated_at)
                WHERE id = :id
                """
            ),
            {
                "id": existing["id"],
                "name": "Super Admin",
                "password_hash": password_hash,
                "role_name": "Super Admin",
                "updated_at": now,
            },
        )
        return
    values = {
        "id": str(uuid4()),
        "name": "Super Admin",
        "email": "admin@devita.local",
        "password_hash": password_hash,
        "role_name": "Super Admin",
        "created_at": now,
        "updated_at": now,
    }
    if _users_id_is_auto_increment(conn):
        conn.execute(
            text(
                """
                INSERT INTO users (
                    name, email, password_hash, role_name, is_active,
                    created_by_user_id, created_at, updated_at
                ) VALUES (
                    :name, :email, :password_hash, :role_name, TRUE,
                    NULL, :created_at, :updated_at
                )
                """
            ),
            values,
        )
    else:
        conn.execute(
            text(
                """
                INSERT INTO users (
                    id, name, email, password_hash, role_name, is_active,
                    created_by_user_id, created_at, updated_at
                ) VALUES (
                    :id, :name, :email, :password_hash, :role_name, TRUE,
                    NULL, :created_at, :updated_at
                )
                """
            ),
            values,
        )


def _ensure_user_columns(conn: Any) -> None:
    columns = {
        "id": "VARCHAR(36) NULL",
        "name": "VARCHAR(150) NULL",
        "email": "VARCHAR(255) NULL",
        "password_hash": "VARCHAR(255) NULL",
        "role_name": "VARCHAR(100) NOT NULL DEFAULT 'Team Member'",
        "is_active": "BOOLEAN NOT NULL DEFAULT TRUE",
        "created_by_user_id": "VARCHAR(36) NULL",
        "created_at": "DATETIME NULL",
        "updated_at": "DATETIME NULL",
    }
    for name, definition in columns.items():
        exists = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'users'
                  AND COLUMN_NAME = :name
                """
            ),
            {"name": name},
        ).scalar()
        if not exists:
            conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {definition}"))


def _users_id_is_auto_increment(conn: Any | None = None) -> bool:
    should_close = conn is None
    connection = conn or get_engine().connect()
    try:
        row = connection.execute(
            text(
                """
                SELECT EXTRA
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'users'
                  AND COLUMN_NAME = 'id'
                LIMIT 1
                """
            )
        ).mappings().first()
        return "auto_increment" in str(row.get("EXTRA") if row else "").lower()
    finally:
        if should_close:
            connection.close()


def _hash_password(password: str) -> str:
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return f"pbkdf2_sha256$120000${_b64(salt)}${_b64(digest)}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, rounds, salt_raw, digest_raw = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = _unb64(salt_raw)
        expected = _unb64(digest_raw)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(rounds))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _normalize_email(email: Any) -> str:
    value = str(email or "").strip().lower()
    if "@" not in value:
        raise ValueError("A valid email address is required.")
    return value


def _normalize_role(role_name: Any) -> str:
    value = str(role_name or "Team Member").strip()
    return value if value in DEFAULT_ROLES else value or "Team Member"


def _public_user(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": str(row["name"]),
        "email": str(row["email"]),
        "role_name": str(row.get("role_name") or "Team Member"),
        "is_active": bool(row.get("is_active")),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _sign(payload_raw: str) -> str:
    digest = hmac.new(
        get_settings().auth_secret_key.encode("utf-8"),
        payload_raw.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _b64(digest)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
