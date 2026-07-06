import re
from typing import Any

from app.db import fetch_rows
from app.services.ai_sql_attempt_store import get_attempt
from app.services.schema_service import schema_service
from app.services.sql_safety_validator import validate_sql_safety


def preview_attempt_rows(attempt_id: str, limit: int = 25) -> dict[str, Any]:
    attempt = get_attempt(attempt_id)
    if not attempt:
        raise ValueError("AI SQL attempt was not found.")

    sql = str(attempt.get("final_sql") or "").strip()
    if not sql:
        return _empty(attempt_id, limit, "No final SQL is available for this attempt.")

    schema = schema_service.get_schema(force_refresh=False)
    validation = validate_sql_safety(sql, schema, require_limit=False)
    if not validation.isValid:
        return _empty(attempt_id, limit, validation.reason)

    preview_sql = _with_preview_limit(sql, limit)
    try:
        columns, rows = fetch_rows(preview_sql)
    except Exception as exc:
        return _empty(attempt_id, limit, str(exc))

    return {
        "attempt_id": attempt_id,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "preview_limit": limit,
        "execution_status": "success",
        "error": None,
    }


def _with_preview_limit(sql: str, limit: int) -> str:
    cleaned = sql.strip().rstrip(";")
    existing_limit = re.search(r"\blimit\s+(\d+)\s*$", cleaned, re.IGNORECASE)
    if existing_limit:
        current_limit = int(existing_limit.group(1))
        if current_limit <= limit:
            return cleaned
        return re.sub(r"\blimit\s+\d+\s*$", f"LIMIT {limit}", cleaned, flags=re.IGNORECASE)
    return f"{cleaned}\nLIMIT {limit}"


def _empty(attempt_id: str, limit: int, error: str) -> dict[str, Any]:
    return {
        "attempt_id": attempt_id,
        "columns": [],
        "rows": [],
        "row_count": 0,
        "preview_limit": limit,
        "execution_status": "failed",
        "error": error,
    }
