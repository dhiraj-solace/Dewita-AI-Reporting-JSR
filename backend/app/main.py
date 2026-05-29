from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from app.core.config import get_settings
from app.db import get_engine
from app.models import AiSqlAttempt, AiSqlAttemptEvent, AiSqlAttemptPreview, AiSqlAttemptReviewRequest, GeneratedReport, ReportAuditLog, ReportRequest, RoleReportPermissionsPayload, SavedReportShareRequest, SavedReportShareResponse, SavedReportSummary, ScheduledReport, ScheduledReportCreate, ScheduledReportRun, ScheduledReportUpdate, SqlMistakeExample
from app.services.catalog import load_report_catalog, load_report_categories, load_schema_catalog
from app.services.ai_sql_attempt_store import get_attempt, list_attempt_events, list_attempts, review_attempt
from app.services.admin_attempt_preview import preview_attempt_rows
from app.services.audit_log import create_audit_log, list_audit_logs
from app.services.email_service import share_report_email
from app.services.report_permissions import ReportPermissionError, assert_report_permission, list_role_report_permissions, replace_role_report_permissions
from app.services.report_exporter import export_filename, export_report_pdf, export_report_xlsx
from app.services.saved_report_store import get_saved_report, list_saved_reports, save_generated_report
from app.services.scheduled_reports import (
    create_scheduled_report,
    get_scheduled_report,
    list_scheduled_report_runs,
    list_scheduled_reports,
    run_scheduled_report_now,
    set_scheduled_report_status,
    start_scheduler_loop,
    stop_scheduler_loop,
    update_scheduled_report,
)
from app.services.sql_mistake_store import list_mistake_examples
from app.services.report_runner import ReportBuildError, build_report

settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_super_admin(actor_role: str | None) -> None:
    if (actor_role or "").strip().lower() != "super admin":
        raise HTTPException(status_code=403, detail="Only Super Admin can manage and run scheduled reports.")


def _normalize_share_formats(formats: list[str]) -> list[str]:
    normalized = []
    for item in formats or []:
        value = str(item).strip().lower()
        if value == "excel":
            value = "xlsx"
        if value not in {"pdf", "xlsx"}:
            raise ValueError("Share format must be pdf or xlsx.")
        if value not in normalized:
            normalized.append(value)
    if not normalized:
        raise ValueError("Select at least one share format.")
    return normalized


@app.on_event("startup")
async def startup() -> None:
    await start_scheduler_loop()


@app.on_event("shutdown")
async def shutdown() -> None:
    await stop_scheduler_loop()


@app.get("/health")
def health() -> dict:
    db_configured = settings.resolved_database_url is not None
    db_connected = False
    if db_configured:
        try:
            with get_engine().connect() as conn:
                conn.exec_driver_sql("SELECT 1")
            db_connected = True
        except Exception:
            db_connected = False
    return {
        "ok": True,
        "database_configured": db_configured,
        "database_connected": db_connected,
        "ai_enabled": bool(
            settings.ai_sql_enabled
            and (
                settings.ai_provider.lower() == "ollama"
                or bool(settings.openrouter_api_key)
                or settings.gemini_api_key
                or settings.openai_api_key
            )
        ),
    }


@app.get("/api/schema")
def schema_catalog() -> dict:
    return load_schema_catalog()


@app.post("/api/schema/refresh")
def refresh_schema() -> dict:
    try:
        from app.services.schema_service import schema_service
        return schema_service.refresh_schema()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/reports/catalog")
def report_catalog() -> dict:
    return load_report_catalog()


@app.get("/api/reports/categories")
def report_categories() -> dict:
    return load_report_categories()


@app.get("/api/admin/report-permissions")
def admin_report_permissions() -> dict:
    try:
        return list_role_report_permissions()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.put("/api/admin/report-permissions")
def admin_update_report_permissions(
    payload: RoleReportPermissionsPayload,
    actor_role: str | None = Query(default="Super Admin"),
) -> dict:
    try:
        return replace_role_report_permissions(
            [item.model_dump() for item in payload.permissions],
            actor_role=actor_role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/report-audit-logs", response_model=list[ReportAuditLog])
def admin_report_audit_logs(limit: int = Query(default=100, ge=1, le=300)) -> list[ReportAuditLog]:
    try:
        return [ReportAuditLog.model_validate(item) for item in list_audit_logs(limit)]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/scheduled-reports", response_model=list[ScheduledReport])
def admin_scheduled_reports(actor_role: str | None = Query(default="Super Admin")) -> list[ScheduledReport]:
    _require_super_admin(actor_role)
    try:
        return [ScheduledReport.model_validate(item) for item in list_scheduled_reports()]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/admin/scheduled-reports", response_model=ScheduledReport)
def admin_create_scheduled_report(
    payload: ScheduledReportCreate,
    actor_role: str | None = Query(default="Super Admin"),
) -> ScheduledReport:
    _require_super_admin(actor_role)
    try:
        return ScheduledReport.model_validate(create_scheduled_report(payload.model_dump(), actor_role or "Super Admin"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/scheduled-reports/{schedule_id}", response_model=ScheduledReport)
def admin_scheduled_report(
    schedule_id: str,
    actor_role: str | None = Query(default="Super Admin"),
) -> ScheduledReport:
    _require_super_admin(actor_role)
    try:
        schedule = get_scheduled_report(schedule_id)
        if schedule is None:
            raise HTTPException(status_code=404, detail="Scheduled report was not found.")
        return ScheduledReport.model_validate(schedule)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.put("/api/admin/scheduled-reports/{schedule_id}", response_model=ScheduledReport)
def admin_update_scheduled_report(
    schedule_id: str,
    payload: ScheduledReportUpdate,
    actor_role: str | None = Query(default="Super Admin"),
) -> ScheduledReport:
    _require_super_admin(actor_role)
    try:
        return ScheduledReport.model_validate(update_scheduled_report(schedule_id, payload.model_dump(), actor_role or "Super Admin"))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.patch("/api/admin/scheduled-reports/{schedule_id}/status", response_model=ScheduledReport)
def admin_update_scheduled_report_status(
    schedule_id: str,
    is_active: bool,
    actor_role: str | None = Query(default="Super Admin"),
) -> ScheduledReport:
    _require_super_admin(actor_role)
    try:
        return ScheduledReport.model_validate(set_scheduled_report_status(schedule_id, is_active, actor_role or "Super Admin"))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/admin/scheduled-reports/{schedule_id}/run-now", response_model=ScheduledReportRun)
async def admin_run_scheduled_report_now(
    schedule_id: str,
    actor_role: str | None = Query(default="Super Admin"),
) -> ScheduledReportRun:
    _require_super_admin(actor_role)
    try:
        return ScheduledReportRun.model_validate(await run_scheduled_report_now(schedule_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/scheduled-reports/{schedule_id}/runs", response_model=list[ScheduledReportRun])
def admin_scheduled_report_runs(
    schedule_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    actor_role: str | None = Query(default="Super Admin"),
) -> list[ScheduledReportRun]:
    _require_super_admin(actor_role)
    try:
        return [ScheduledReportRun.model_validate(item) for item in list_scheduled_report_runs(schedule_id, limit)]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/reports/query", response_model=GeneratedReport)
async def query_report(request: ReportRequest) -> GeneratedReport:
    try:
        report = await build_report(request)
        if report.generated_source == "cache":
            return report
        try:
            assert_report_permission(request.current_user_role, report.report_category or "custom", "save")
        except ReportPermissionError:
            return report
        saved_report_id = save_generated_report(report)
        return report.model_copy(update={"saved_report_id": saved_report_id})
    except ReportBuildError as exc:
        raise HTTPException(
            status_code=exc.status_code or 400,
            detail={
                "title": exc.title,
                "message": str(exc),
                "solution": exc.solution,
                "status_code": exc.status_code,
                "attempt_id": exc.attempt_id,
                "retry_attempts": [attempt.model_dump() for attempt in exc.attempts],
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/reports/saved", response_model=list[SavedReportSummary])
def saved_reports(
    limit: int = Query(default=50, ge=1, le=200),
    role: str | None = Query(default="Super Admin"),
) -> list[SavedReportSummary]:
    try:
        return [SavedReportSummary.model_validate(report) for report in list_saved_reports(limit, role)]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/reports/saved/{report_id}", response_model=GeneratedReport)
def saved_report(report_id: str, role: str | None = Query(default="Super Admin")) -> GeneratedReport:
    try:
        report = get_saved_report(report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Saved report was not found.")
        try:
            assert_report_permission(role, report.report_category or "custom", "view_saved")
        except ReportPermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        return report
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/reports/saved/{report_id}/export/{format}")
def export_saved_report(
    report_id: str,
    format: str,
    role: str | None = Query(default="Super Admin"),
) -> Response:
    try:
        report = get_saved_report(report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Saved report was not found.")
        try:
            assert_report_permission(role, report.report_category or "custom", "export")
        except ReportPermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        normalized_format = format.lower()
        if normalized_format == "pdf":
            content = export_report_pdf(report)
            media_type = "application/pdf"
            filename = export_filename(report, "pdf")
        elif normalized_format in {"xlsx", "excel"}:
            content = export_report_xlsx(report)
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = export_filename(report, "xlsx")
        else:
            raise HTTPException(status_code=400, detail="Export format must be pdf or xlsx.")
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/reports/saved/{report_id}/share", response_model=SavedReportShareResponse)
def share_saved_report(report_id: str, payload: SavedReportShareRequest) -> SavedReportShareResponse:
    try:
        report = get_saved_report(report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Saved report was not found.")
        role = payload.current_user_role or "Super Admin"
        try:
            assert_report_permission(role, report.report_category or "custom", "view_saved")
            if payload.formats:
                assert_report_permission(role, report.report_category or "custom", "export")
        except ReportPermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

        formats = _normalize_share_formats(payload.formats)
        report_for_email = report.model_copy(update={"saved_report_id": report_id})
        delivery = share_report_email(
            report_for_email,
            payload.recipient_email,
            formats,
            payload.message,
        )
        create_audit_log(
            event_type="report_shared",
            actor_role=role,
            report_id=report_id,
            report_category=report.report_category or "custom",
            action="share",
            metadata={
                "recipient_email": payload.recipient_email,
                "formats": formats,
                "delivery": delivery,
            },
        )
        if delivery.get("status") == "sent":
            message = "Report shared successfully."
        elif delivery.get("status") == "skipped":
            reason = str(delivery.get("reason") or "Email delivery was not attempted.")
            message = f"Share recorded, but email delivery was skipped: {reason}"
        else:
            reason = str(delivery.get("reason") or "Email delivery failed.")
            message = f"Share recorded, but email delivery failed: {reason}"
        return SavedReportShareResponse(status=str(delivery.get("status") or "unknown"), message=message, delivery=delivery)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/ai-sql-attempts", response_model=list[AiSqlAttempt])
def admin_ai_sql_attempts(
    limit: int = Query(default=50, ge=1, le=200),
    gold_only: bool = False,
) -> list[AiSqlAttempt]:
    try:
        return [AiSqlAttempt.model_validate(attempt) for attempt in list_attempts(limit, gold_only)]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/ai-sql-attempts/{attempt_id}", response_model=AiSqlAttempt)
def admin_ai_sql_attempt(attempt_id: str) -> AiSqlAttempt:
    try:
        attempt = get_attempt(attempt_id)
        if attempt is None:
            raise HTTPException(status_code=404, detail="AI SQL attempt was not found.")
        return AiSqlAttempt.model_validate(attempt)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/ai-sql-attempts/{attempt_id}/events", response_model=list[AiSqlAttemptEvent])
def admin_ai_sql_attempt_events(
    attempt_id: str,
    limit: int = Query(default=200, ge=1, le=500),
) -> list[AiSqlAttemptEvent]:
    try:
        if get_attempt(attempt_id) is None:
            raise HTTPException(status_code=404, detail="AI SQL attempt was not found.")
        return [AiSqlAttemptEvent.model_validate(event) for event in list_attempt_events(attempt_id, limit)]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/admin/ai-sql-attempts/{attempt_id}/review", response_model=AiSqlAttempt)
def admin_review_ai_sql_attempt(attempt_id: str, review: AiSqlAttemptReviewRequest) -> AiSqlAttempt:
    try:
        return AiSqlAttempt.model_validate(
            review_attempt(
                attempt_id,
                user_feedback_status=review.user_feedback_status,
                admin_approved=review.admin_approved,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/ai-sql-attempts/{attempt_id}/preview", response_model=AiSqlAttemptPreview)
def admin_ai_sql_attempt_preview(
    attempt_id: str,
    limit: int = Query(default=25, ge=1, le=100),
) -> AiSqlAttemptPreview:
    try:
        return AiSqlAttemptPreview.model_validate(preview_attempt_rows(attempt_id, limit))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/sql-mistake-examples", response_model=list[SqlMistakeExample])
def admin_sql_mistake_examples(limit: int = Query(default=100, ge=1, le=200)) -> list[SqlMistakeExample]:
    try:
        return [SqlMistakeExample.model_validate(item) for item in list_mistake_examples(limit)]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
