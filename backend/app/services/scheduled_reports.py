import asyncio
import json
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from app.db import get_engine
from app.models import ReportRequest
from app.services.audit_log import create_audit_log
from app.services.email_service import send_report_email
from app.services.report_permissions import ReportPermissionError, assert_report_permission
from app.services.report_runner import build_report
from app.services.saved_report_store import save_generated_report


SCHEDULER_POLL_SECONDS = 60
_SCHEDULER_TASK: asyncio.Task | None = None
_SCHEDULER_STOP = asyncio.Event()


def ensure_scheduled_report_tables() -> None:
    scheduled_reports_ddl = """
    CREATE TABLE IF NOT EXISTS scheduled_reports (
        id VARCHAR(36) PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        report_category VARCHAR(100) NOT NULL,
        question TEXT NOT NULL,
        frequency VARCHAR(20) NOT NULL,
        schedule_time VARCHAR(5) NOT NULL,
        timezone VARCHAR(100) NOT NULL DEFAULT 'Asia/Calcutta',
        filters_json LONGTEXT NULL,
        recipients_json LONGTEXT NULL,
        current_user_role VARCHAR(100) NOT NULL DEFAULT 'Super Admin',
        sql_generation_provider VARCHAR(50) NULL,
        result_limit INT NOT NULL DEFAULT 500,
        dry_run BOOLEAN NOT NULL DEFAULT FALSE,
        export_formats_json LONGTEXT NULL,
        execution_settings_json LONGTEXT NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        next_run_at DATETIME NULL,
        last_run_at DATETIME NULL,
        last_status VARCHAR(50) NULL,
        last_error LONGTEXT NULL,
        created_by_role VARCHAR(100) NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        INDEX idx_scheduled_reports_due (is_active, next_run_at)
    )
    """
    runs_ddl = """
    CREATE TABLE IF NOT EXISTS scheduled_report_runs (
        id VARCHAR(36) PRIMARY KEY,
        scheduled_report_id VARCHAR(36) NOT NULL,
        saved_report_id VARCHAR(36) NULL,
        status VARCHAR(50) NOT NULL,
        started_at DATETIME NULL,
        finished_at DATETIME NULL,
        error_message LONGTEXT NULL,
        generated_row_count INT NULL,
        metadata_json LONGTEXT NULL,
        INDEX idx_scheduled_report_runs_schedule (scheduled_report_id),
        INDEX idx_scheduled_report_runs_started (started_at)
    )
    """
    with get_engine().begin() as conn:
        conn.execute(text(scheduled_reports_ddl))
        conn.execute(text(runs_ddl))


def list_scheduled_reports() -> list[dict[str, Any]]:
    ensure_scheduled_report_tables()
    with get_engine().connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM scheduled_reports ORDER BY updated_at DESC")
        ).mappings().all()
    return [_row_to_schedule(dict(row)) for row in rows]


def get_scheduled_report(schedule_id: str) -> dict[str, Any] | None:
    ensure_scheduled_report_tables()
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT * FROM scheduled_reports WHERE id = :id"),
            {"id": schedule_id},
        ).mappings().first()
    return _row_to_schedule(dict(row)) if row else None


def create_scheduled_report(payload: dict[str, Any], actor_role: str = "Super Admin") -> dict[str, Any]:
    ensure_scheduled_report_tables()
    now = _now()
    schedule_id = str(uuid4())
    normalized = _normalize_schedule_payload(payload)
    row = {
        **normalized,
        "id": schedule_id,
        "next_run_at": _next_run_at(normalized["frequency"], normalized["schedule_time"], None),
        "last_run_at": None,
        "last_status": None,
        "last_error": None,
        "created_by_role": actor_role,
        "created_at": now,
        "updated_at": now,
    }
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO scheduled_reports (
                    id, name, report_category, question, frequency, schedule_time, timezone,
                    filters_json, recipients_json, current_user_role, sql_generation_provider,
                    result_limit, dry_run, export_formats_json, execution_settings_json,
                    is_active, next_run_at, last_run_at, last_status, last_error,
                    created_by_role, created_at, updated_at
                ) VALUES (
                    :id, :name, :report_category, :question, :frequency, :schedule_time, :timezone,
                    :filters_json, :recipients_json, :current_user_role, :sql_generation_provider,
                    :result_limit, :dry_run, :export_formats_json, :execution_settings_json,
                    :is_active, :next_run_at, :last_run_at, :last_status, :last_error,
                    :created_by_role, :created_at, :updated_at
                )
                """
            ),
            row,
        )
    create_audit_log(
        event_type="scheduled_report_created",
        actor_role=actor_role,
        report_category=row["report_category"],
        action="create_schedule",
        after=_public_schedule(row),
    )
    created = get_scheduled_report(schedule_id)
    if created is None:
        raise ValueError("Scheduled report was not found after creation.")
    return created


def update_scheduled_report(schedule_id: str, payload: dict[str, Any], actor_role: str = "Super Admin") -> dict[str, Any]:
    ensure_scheduled_report_tables()
    before = get_scheduled_report(schedule_id)
    if before is None:
        raise ValueError("Scheduled report was not found.")
    normalized = _normalize_schedule_payload(payload)
    next_run_at = _next_run_at(normalized["frequency"], normalized["schedule_time"], None)
    update_payload = {
        **normalized,
        "id": schedule_id,
        "next_run_at": next_run_at,
        "updated_at": _now(),
    }
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                UPDATE scheduled_reports
                SET name = :name,
                    report_category = :report_category,
                    question = :question,
                    frequency = :frequency,
                    schedule_time = :schedule_time,
                    timezone = :timezone,
                    filters_json = :filters_json,
                    recipients_json = :recipients_json,
                    current_user_role = :current_user_role,
                    sql_generation_provider = :sql_generation_provider,
                    result_limit = :result_limit,
                    dry_run = :dry_run,
                    export_formats_json = :export_formats_json,
                    execution_settings_json = :execution_settings_json,
                    is_active = :is_active,
                    next_run_at = :next_run_at,
                    updated_at = :updated_at
                WHERE id = :id
                """
            ),
            update_payload,
        )
    after = get_scheduled_report(schedule_id)
    create_audit_log(
        event_type="scheduled_report_updated",
        actor_role=actor_role,
        report_category=normalized["report_category"],
        action="update_schedule",
        before=before,
        after=after,
    )
    if after is None:
        raise ValueError("Scheduled report was not found after update.")
    return after


def set_scheduled_report_status(schedule_id: str, is_active: bool, actor_role: str = "Super Admin") -> dict[str, Any]:
    ensure_scheduled_report_tables()
    before = get_scheduled_report(schedule_id)
    if before is None:
        raise ValueError("Scheduled report was not found.")
    next_run_at = _next_run_at(before["frequency"], before["schedule_time"], None) if is_active else None
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                UPDATE scheduled_reports
                SET is_active = :is_active,
                    next_run_at = :next_run_at,
                    updated_at = :updated_at
                WHERE id = :id
                """
            ),
            {"id": schedule_id, "is_active": is_active, "next_run_at": next_run_at, "updated_at": _now()},
        )
    after = get_scheduled_report(schedule_id)
    create_audit_log(
        event_type="scheduled_report_status_changed",
        actor_role=actor_role,
        report_category=before.get("report_category"),
        action="enable_schedule" if is_active else "disable_schedule",
        before=before,
        after=after,
    )
    if after is None:
        raise ValueError("Scheduled report was not found after status update.")
    return after


def list_scheduled_report_runs(schedule_id: str, limit: int = 50) -> list[dict[str, Any]]:
    ensure_scheduled_report_tables()
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT * FROM scheduled_report_runs
                WHERE scheduled_report_id = :scheduled_report_id
                ORDER BY started_at DESC
                LIMIT :limit
                """
            ),
            {"scheduled_report_id": schedule_id, "limit": limit},
        ).mappings().all()
    return [dict(row) for row in rows]


async def run_scheduled_report_now(schedule_id: str) -> dict[str, Any]:
    schedule = get_scheduled_report(schedule_id)
    if schedule is None:
        raise ValueError("Scheduled report was not found.")
    return await _run_schedule(schedule, triggered_by="manual")


async def run_due_scheduled_reports(limit: int = 5) -> list[dict[str, Any]]:
    ensure_scheduled_report_tables()
    now = _now()
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT * FROM scheduled_reports
                WHERE is_active = TRUE
                  AND next_run_at IS NOT NULL
                  AND next_run_at <= :now
                ORDER BY next_run_at ASC
                LIMIT :limit
                """
            ),
            {"now": now, "limit": limit},
        ).mappings().all()
    results = []
    for row in rows:
        results.append(await _run_schedule(_row_to_schedule(dict(row)), triggered_by="scheduler"))
    return results


async def start_scheduler_loop() -> None:
    global _SCHEDULER_TASK, _SCHEDULER_STOP
    if _SCHEDULER_TASK and not _SCHEDULER_TASK.done():
        return
    _SCHEDULER_STOP = asyncio.Event()
    _SCHEDULER_TASK = asyncio.create_task(_scheduler_loop())


async def stop_scheduler_loop() -> None:
    if _SCHEDULER_TASK and not _SCHEDULER_TASK.done():
        _SCHEDULER_STOP.set()
        await asyncio.wait([_SCHEDULER_TASK], timeout=5)


async def _scheduler_loop() -> None:
    while not _SCHEDULER_STOP.is_set():
        try:
            await run_due_scheduled_reports()
        except Exception:
            pass
        try:
            await asyncio.wait_for(_SCHEDULER_STOP.wait(), timeout=SCHEDULER_POLL_SECONDS)
        except asyncio.TimeoutError:
            pass


async def _run_schedule(schedule: dict[str, Any], triggered_by: str) -> dict[str, Any]:
    run_id = str(uuid4())
    started_at = _now()
    _insert_run(run_id, schedule["id"], "running", started_at)
    saved_report_id = None
    status = "success"
    error_message = None
    row_count = 0
    delivery_result: dict[str, Any] = {"status": "skipped", "reason": "Report was not generated."}
    try:
        assert_report_permission(schedule["current_user_role"], schedule["report_category"], "create")
        request = _schedule_to_report_request(schedule)
        report = await build_report(request)
        row_count = report.row_count
        try:
            assert_report_permission(schedule["current_user_role"], report.report_category or schedule["report_category"], "save")
            saved_report_id = save_generated_report(report)
        except ReportPermissionError as exc:
            raise ValueError(str(exc)) from exc
        report_for_delivery = report.model_copy(update={"saved_report_id": saved_report_id})
        delivery_result = _deliver_scheduled_report(report_for_delivery, schedule)
    except Exception as exc:
        status = "failed"
        error_message = str(exc)
    finished_at = _now()
    _finish_run(
        run_id,
        status,
        finished_at,
        saved_report_id,
        error_message,
        row_count,
        {
            "triggered_by": triggered_by,
            "recipients": schedule.get("recipients") or {},
            "delivery": delivery_result,
        },
    )
    _update_schedule_after_run(schedule, status, error_message)
    create_audit_log(
        event_type="scheduled_report_run",
        actor_role=schedule.get("current_user_role"),
        report_id=saved_report_id,
        report_category=schedule.get("report_category"),
        action=triggered_by,
        metadata={
            "schedule_id": schedule["id"],
            "run_id": run_id,
            "status": status,
            "error": error_message,
            "delivery": delivery_result,
        },
    )
    return get_run(run_id) or {"id": run_id, "status": status}


def _deliver_scheduled_report(report: Any, schedule: dict[str, Any]) -> dict[str, Any]:
    recipients = schedule.get("recipients") or {}
    emails = recipients.get("emails") if isinstance(recipients, dict) else []
    formats = schedule.get("export_formats") or ["xlsx"]
    return send_report_email(report, emails if isinstance(emails, list) else [], formats)


def get_run(run_id: str) -> dict[str, Any] | None:
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT * FROM scheduled_report_runs WHERE id = :id"),
            {"id": run_id},
        ).mappings().first()
    return dict(row) if row else None


def _schedule_to_report_request(schedule: dict[str, Any]) -> ReportRequest:
    filters = schedule.get("filters") or {}
    start_date, end_date = _resolve_date_filter(filters)
    return ReportRequest(
        question=schedule["question"],
        report_category=schedule["report_category"],
        current_user_role=schedule["current_user_role"],
        start_date=start_date,
        end_date=end_date,
        limit=int(schedule["limit"]),
        dry_run=bool(schedule["dry_run"]),
        sql_generation_provider=schedule.get("sql_generation_provider"),
    )


def _insert_run(run_id: str, schedule_id: str, status: str, started_at: datetime) -> None:
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO scheduled_report_runs (
                    id, scheduled_report_id, status, started_at
                ) VALUES (
                    :id, :scheduled_report_id, :status, :started_at
                )
                """
            ),
            {"id": run_id, "scheduled_report_id": schedule_id, "status": status, "started_at": started_at},
        )


def _finish_run(
    run_id: str,
    status: str,
    finished_at: datetime,
    saved_report_id: str | None,
    error_message: str | None,
    row_count: int,
    metadata: dict[str, Any],
) -> None:
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                UPDATE scheduled_report_runs
                SET status = :status,
                    finished_at = :finished_at,
                    saved_report_id = :saved_report_id,
                    error_message = :error_message,
                    generated_row_count = :generated_row_count,
                    metadata_json = :metadata_json
                WHERE id = :id
                """
            ),
            {
                "id": run_id,
                "status": status,
                "finished_at": finished_at,
                "saved_report_id": saved_report_id,
                "error_message": error_message,
                "generated_row_count": row_count,
                "metadata_json": _json(metadata),
            },
        )


def _update_schedule_after_run(schedule: dict[str, Any], status: str, error_message: str | None) -> None:
    now = _now()
    next_run_at = _next_run_at(schedule["frequency"], schedule["schedule_time"], now)
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                UPDATE scheduled_reports
                SET last_run_at = :last_run_at,
                    last_status = :last_status,
                    last_error = :last_error,
                    next_run_at = :next_run_at,
                    updated_at = :updated_at
                WHERE id = :id
                """
            ),
            {
                "id": schedule["id"],
                "last_run_at": now,
                "last_status": status,
                "last_error": error_message,
                "next_run_at": next_run_at,
                "updated_at": now,
            },
        )


def _normalize_schedule_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(payload.get("name") or "").strip(),
        "report_category": str(payload.get("report_category") or "custom").strip(),
        "question": str(payload.get("question") or "").strip(),
        "frequency": str(payload.get("frequency") or "daily").strip().lower(),
        "schedule_time": _normalize_schedule_time(str(payload.get("schedule_time") or "09:00")),
        "timezone": str(payload.get("timezone") or "Asia/Calcutta").strip(),
        "filters_json": _json(payload.get("filters") or {}),
        "recipients_json": _json(payload.get("recipients") or {}),
        "current_user_role": str(payload.get("current_user_role") or "Super Admin").strip(),
        "sql_generation_provider": payload.get("sql_generation_provider"),
        "result_limit": int(payload.get("limit") or 500),
        "dry_run": bool(payload.get("dry_run")),
        "export_formats_json": _json(payload.get("export_formats") or []),
        "execution_settings_json": _json(payload.get("execution_settings") or {}),
        "is_active": bool(payload.get("is_active", True)),
    }


def _row_to_schedule(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "report_category": row["report_category"],
        "question": row["question"],
        "frequency": row["frequency"],
        "schedule_time": row["schedule_time"],
        "timezone": row["timezone"],
        "filters": _loads(row.get("filters_json"), {}),
        "recipients": _loads(row.get("recipients_json"), {}),
        "current_user_role": row["current_user_role"],
        "sql_generation_provider": row.get("sql_generation_provider"),
        "limit": int(row.get("result_limit") or 500),
        "dry_run": bool(row.get("dry_run")),
        "export_formats": _loads(row.get("export_formats_json"), []),
        "execution_settings": _loads(row.get("execution_settings_json"), {}),
        "is_active": bool(row.get("is_active")),
        "next_run_at": row.get("next_run_at"),
        "last_run_at": row.get("last_run_at"),
        "last_status": row.get("last_status"),
        "last_error": row.get("last_error"),
        "created_by_role": row.get("created_by_role"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _public_schedule(row: dict[str, Any]) -> dict[str, Any]:
    public = dict(row)
    public["filters"] = _loads(public.pop("filters_json", None), {})
    public["recipients"] = _loads(public.pop("recipients_json", None), {})
    public["export_formats"] = _loads(public.pop("export_formats_json", None), [])
    public["execution_settings"] = _loads(public.pop("execution_settings_json", None), {})
    return public


def _next_run_at(frequency: str, schedule_time: str, after: datetime | None) -> datetime:
    base = after or _now()
    hour, minute = [int(part) for part in schedule_time.split(":", 1)]
    candidate = datetime.combine(base.date(), time(hour=hour, minute=minute))
    if candidate <= base:
        if frequency == "daily":
            candidate += timedelta(days=1)
        elif frequency == "weekly":
            candidate += timedelta(days=7)
        else:
            candidate = _add_month(candidate)
    return candidate


def _add_month(value: datetime) -> datetime:
    year = value.year + (1 if value.month == 12 else 0)
    month = 1 if value.month == 12 else value.month + 1
    day = min(value.day, _days_in_month(year, month))
    return value.replace(year=year, month=month, day=day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - timedelta(days=1)).day


def _resolve_date_filter(filters: dict[str, Any]) -> tuple[str | None, str | None]:
    if filters.get("start_date") or filters.get("end_date"):
        return filters.get("start_date"), filters.get("end_date")
    preset = str(filters.get("date_preset") or "").strip().lower()
    today = date.today()
    if preset == "today":
        return today.isoformat(), today.isoformat()
    if preset == "yesterday":
        value = today - timedelta(days=1)
        return value.isoformat(), value.isoformat()
    if preset == "current_week":
        start = today - timedelta(days=today.weekday())
        return start.isoformat(), (start + timedelta(days=6)).isoformat()
    if preset == "previous_week":
        start = today - timedelta(days=today.weekday() + 7)
        return start.isoformat(), (start + timedelta(days=6)).isoformat()
    if preset == "current_month":
        start = today.replace(day=1)
        end = start.replace(day=_days_in_month(start.year, start.month))
        return start.isoformat(), end.isoformat()
    if preset == "previous_month":
        first = today.replace(day=1)
        previous_end = first - timedelta(days=1)
        previous_start = previous_end.replace(day=1)
        return previous_start.isoformat(), previous_end.isoformat()
    return None, None


def _normalize_schedule_time(value: str) -> str:
    hour, minute = [int(part) for part in value.split(":", 1)]
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("Schedule time must be HH:MM in 24-hour format.")
    return f"{hour:02d}:{minute:02d}"


def _loads(value: Any, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
