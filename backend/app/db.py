from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.core.config import get_settings

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        database_url = get_settings().resolved_database_url
        if not database_url:
            raise RuntimeError(
                "Database is not configured. Set DATABASE_URL or DB_HOST/DB_NAME/DB_USER/DB_PASSWORD."
            )
        timeout = max(1, get_settings().query_timeout_seconds)
        _engine = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_recycle=280,
            connect_args={"read_timeout": timeout, "write_timeout": timeout},
        )
    return _engine


def fetch_rows(sql: str, params: Mapping[str, Any] | None = None) -> tuple[list[str], list[dict[str, Any]]]:
    with get_engine().connect() as conn:
        result = conn.execute(text(sql), params or {})
        rows: Sequence[Any] = result.fetchall()
        columns = list(result.keys())
    return columns, [dict(zip(columns, row, strict=False)) for row in rows]
