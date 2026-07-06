from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from app.core.config import get_settings
from app.db import get_engine
from app.models import AiSqlAttempt, AiSqlAttemptEvent, AiSqlAttemptPreview, AiSqlAttemptReviewRequest, AuthResponse, GeneratedReport, LoginRequest, ReportAuditLog, ReportRequest, RoleReportPermissionsPayload, SavedReportShareRequest, SavedReportShareResponse, SavedReportSummary, ScheduledReport, ScheduledReportCreate, ScheduledReportRun, ScheduledReportUpdate, SqlMistakeContextUsageRequest, SqlMistakeExample, SqlMistakeGroup, UserCreateRequest, UserPublic, UserUpdateRequest
from app.services.catalog import load_report_catalog, load_report_categories, load_schema_catalog
from app.services.ai_sql_attempt_store import get_attempt, list_attempt_events, list_attempts, review_attempt
from app.services.admin_attempt_preview import preview_attempt_rows
from app.services.audit_log import create_audit_log, list_audit_logs
from app.services.email_service import share_report_email
from app.services.report_permissions import ReportPermissionError, assert_report_permission, list_role_report_permissions, replace_role_report_permissions
from app.services.report_exporter import export_filename, export_report_pdf, export_report_xlsx
from app.services.saved_report_store import get_saved_report, list_saved_reports, save_generated_report
from app.services.saved_report_shares import get_report_share, mark_report_share_viewed, share_saved_report_with_user
from app.services.scheduled_reports import (
    create_scheduled_report,
    get_scheduled_report,
    list_scheduled_report_runs,
    list_scheduled_reports,
    run_due_scheduled_reports,
    run_scheduled_report_now,
    set_scheduled_report_status,
    start_scheduler_loop,
    stop_scheduler_loop,
    update_scheduled_report,
)
from app.services.sql_mistake_store import list_mistake_examples, list_mistake_groups, set_mistake_context_usage, set_mistake_group_context_usage
from app.services.report_runner import ReportBuildError, build_report
from app.services.users import authenticate_user, create_auth_token, create_user, get_user_from_token, list_users, require_super_admin_user, update_user

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


def _current_user(authorization: str | None) -> dict | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return get_user_from_token(token)


def _require_user(authorization: str | None) -> dict:
    user = _current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Login is required.")
    return user


def _require_super_admin_auth(authorization: str | None) -> dict:
    user = _require_user(authorization)
    _require_super_admin(str(user.get("role_name") or ""))
    return user


def _can_access_saved_report(report: GeneratedReport, role: str, user: dict | None, *, require_export: bool = False) -> None:
    is_owner = bool(user and report.created_by_user_id and report.created_by_user_id == user.get("id"))
    is_super_admin = role.strip().lower() == "super admin"
    share = get_report_share(report.saved_report_id or "", user.get("id") if user else None)
    if share and require_export and not bool(share.get("can_export")):
        share = None
    if is_owner or is_super_admin or share:
        return
    action = "export" if require_export else "view_saved"
    assert_report_permission(role, report.report_category or "custom", action)


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
    if settings.scheduler_enabled and not settings.is_vercel:
        await start_scheduler_loop()


@app.on_event("shutdown")
async def shutdown() -> None:
    if settings.scheduler_enabled and not settings.is_vercel:
        await stop_scheduler_loop()


@app.get("/health")
@app.get("/api/health")
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


@app.get("/api/cron/scheduled-reports")
async def cron_scheduled_reports(authorization: str | None = Header(default=None)) -> dict:
    expected = settings.cron_secret
    if not expected or authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Invalid cron authorization.")
    results = await run_due_scheduled_reports(limit=10)
    return {"ok": True, "processed": len(results), "results": results}


@app.post("/api/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest) -> AuthResponse:
    user = authenticate_user(payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return AuthResponse(token=create_auth_token(user), user=UserPublic.model_validate(user))


@app.get("/api/auth/me", response_model=UserPublic)
def me(authorization: str | None = Header(default=None)) -> UserPublic:
    return UserPublic.model_validate(_require_user(authorization))


@app.get("/api/admin/users", response_model=list[UserPublic])
def admin_users(authorization: str | None = Header(default=None)) -> list[UserPublic]:
    user = _require_user(authorization)
    try:
        require_super_admin_user(user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return [UserPublic.model_validate(item) for item in list_users()]


@app.post("/api/admin/users", response_model=UserPublic)
def admin_create_user(payload: UserCreateRequest, authorization: str | None = Header(default=None)) -> UserPublic:
    user = _require_user(authorization)
    try:
        require_super_admin_user(user)
        return UserPublic.model_validate(create_user(payload.model_dump(), user))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/api/admin/users/{user_id}", response_model=UserPublic)
def admin_update_user(
    user_id: str,
    payload: UserUpdateRequest,
    authorization: str | None = Header(default=None),
) -> UserPublic:
    user = _require_user(authorization)
    try:
        require_super_admin_user(user)
        if user.get("id") == user_id and payload.is_active is False:
            raise ValueError("You cannot deactivate your own admin account.")
        return UserPublic.model_validate(update_user(user_id, payload.model_dump(exclude_unset=True), user))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
def admin_report_permissions(authorization: str | None = Header(default=None)) -> dict:
    _require_super_admin_auth(authorization)
    try:
        return list_role_report_permissions()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.put("/api/admin/report-permissions")
def admin_update_report_permissions(
    payload: RoleReportPermissionsPayload,
    actor_role: str | None = Query(default="Super Admin"),
    authorization: str | None = Header(default=None),
) -> dict:
    user = _require_super_admin_auth(authorization)
    try:
        return replace_role_report_permissions(
            [item.model_dump() for item in payload.permissions],
            actor_role=str(user.get("role_name") or actor_role),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/report-audit-logs", response_model=list[ReportAuditLog])
def admin_report_audit_logs(
    limit: int = Query(default=100, ge=1, le=300),
    authorization: str | None = Header(default=None),
) -> list[ReportAuditLog]:
    _require_super_admin_auth(authorization)
    try:
        return [ReportAuditLog.model_validate(item) for item in list_audit_logs(limit)]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/scheduled-reports", response_model=list[ScheduledReport])
def admin_scheduled_reports(
    actor_role: str | None = Query(default="Super Admin"),
    authorization: str | None = Header(default=None),
) -> list[ScheduledReport]:
    _require_super_admin_auth(authorization)
    try:
        return [ScheduledReport.model_validate(item) for item in list_scheduled_reports()]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/admin/scheduled-reports", response_model=ScheduledReport)
def admin_create_scheduled_report(
    payload: ScheduledReportCreate,
    actor_role: str | None = Query(default="Super Admin"),
    authorization: str | None = Header(default=None),
) -> ScheduledReport:
    user = _require_super_admin_auth(authorization)
    try:
        return ScheduledReport.model_validate(create_scheduled_report(payload.model_dump(), str(user.get("role_name") or actor_role or "Super Admin")))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/scheduled-reports/{schedule_id}", response_model=ScheduledReport)
def admin_scheduled_report(
    schedule_id: str,
    actor_role: str | None = Query(default="Super Admin"),
    authorization: str | None = Header(default=None),
) -> ScheduledReport:
    _require_super_admin_auth(authorization)
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
    authorization: str | None = Header(default=None),
) -> ScheduledReport:
    user = _require_super_admin_auth(authorization)
    try:
        return ScheduledReport.model_validate(update_scheduled_report(schedule_id, payload.model_dump(), str(user.get("role_name") or actor_role or "Super Admin")))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.patch("/api/admin/scheduled-reports/{schedule_id}/status", response_model=ScheduledReport)
def admin_update_scheduled_report_status(
    schedule_id: str,
    is_active: bool,
    actor_role: str | None = Query(default="Super Admin"),
    authorization: str | None = Header(default=None),
) -> ScheduledReport:
    user = _require_super_admin_auth(authorization)
    try:
        return ScheduledReport.model_validate(set_scheduled_report_status(schedule_id, is_active, str(user.get("role_name") or actor_role or "Super Admin")))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/admin/scheduled-reports/{schedule_id}/run-now", response_model=ScheduledReportRun)
async def admin_run_scheduled_report_now(
    schedule_id: str,
    actor_role: str | None = Query(default="Super Admin"),
    authorization: str | None = Header(default=None),
) -> ScheduledReportRun:
    _require_super_admin_auth(authorization)
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
    authorization: str | None = Header(default=None),
) -> list[ScheduledReportRun]:
    _require_super_admin_auth(authorization)
    try:
        return [ScheduledReportRun.model_validate(item) for item in list_scheduled_report_runs(schedule_id, limit)]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/reports/query", response_model=GeneratedReport)
async def query_report(request: ReportRequest, authorization: str | None = Header(default=None)) -> GeneratedReport:
    user = _current_user(authorization)
    if user:
        request = request.model_copy(update={"current_user_role": user["role_name"]})
    try:
        report = await build_report(request)
        if user:
            report = report.model_copy(update={"created_by_user_id": user["id"], "created_by_role": user["role_name"]})
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
    authorization: str | None = Header(default=None),
) -> list[SavedReportSummary]:
    user = _current_user(authorization)
    actor_role = str(user.get("role_name")) if user else role
    try:
        return [
            SavedReportSummary.model_validate(report)
            for report in list_saved_reports(limit, actor_role, user.get("id") if user else None)
        ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/reports/saved/{report_id}", response_model=GeneratedReport)
def saved_report(
    report_id: str,
    role: str | None = Query(default="Super Admin"),
    authorization: str | None = Header(default=None),
) -> GeneratedReport:
    user = _current_user(authorization)
    actor_role = str(user.get("role_name")) if user else role
    try:
        report = get_saved_report(report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Saved report was not found.")
        try:
            _can_access_saved_report(report, actor_role or "Super Admin", user)
        except ReportPermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        if user:
            mark_report_share_viewed(report_id, user.get("id"))
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
    access_token: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> Response:
    user = _current_user(authorization) or get_user_from_token(access_token)
    actor_role = str(user.get("role_name")) if user else role
    try:
        report = get_saved_report(report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Saved report was not found.")
        try:
            _can_access_saved_report(report, actor_role or "Super Admin", user, require_export=True)
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
def share_saved_report(
    report_id: str,
    payload: SavedReportShareRequest,
    authorization: str | None = Header(default=None),
) -> SavedReportShareResponse:
    user = _current_user(authorization)
    try:
        report = get_saved_report(report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Saved report was not found.")
        role = str(user.get("role_name")) if user else (payload.current_user_role or "Super Admin")
        try:
            _can_access_saved_report(report, role, user)
            if payload.recipient_email and payload.formats:
                _can_access_saved_report(report, role, user, require_export=True)
        except ReportPermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

        formats = _normalize_share_formats(payload.formats) if payload.recipient_email and payload.formats else []
        share = share_saved_report_with_user(
            report_id=report_id,
            recipient_user_id=payload.recipient_user_id,
            recipient_email=payload.recipient_email,
            actor=user,
            actor_role=role,
            message=payload.message,
            can_export=payload.can_export,
            report_category=report.report_category or "custom",
        )
        report_for_email = report.model_copy(update={"saved_report_id": report_id})
        delivery = {"status": "skipped", "reason": "In-app share only."}
        if payload.recipient_email and formats:
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
                "recipient_user_id": share.get("shared_with_user_id"),
                "formats": formats,
                "can_export": payload.can_export,
                "delivery": delivery,
            },
        )
        if delivery.get("status") == "sent":
            message = "Report shared in app and email was sent."
        elif delivery.get("status") == "skipped":
            reason = str(delivery.get("reason") or "Email delivery was not attempted.")
            message = f"Report shared in app. Email delivery was skipped: {reason}"
        else:
            reason = str(delivery.get("reason") or "Email delivery failed.")
            message = f"Report shared in app, but email delivery failed: {reason}"
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
    authorization: str | None = Header(default=None),
) -> list[AiSqlAttempt]:
    _require_super_admin_auth(authorization)
    try:
        return [AiSqlAttempt.model_validate(attempt) for attempt in list_attempts(limit, gold_only)]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/ai-sql-attempts/{attempt_id}", response_model=AiSqlAttempt)
def admin_ai_sql_attempt(
    attempt_id: str,
    authorization: str | None = Header(default=None),
) -> AiSqlAttempt:
    _require_super_admin_auth(authorization)
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
    authorization: str | None = Header(default=None),
) -> list[AiSqlAttemptEvent]:
    _require_super_admin_auth(authorization)
    try:
        if get_attempt(attempt_id) is None:
            raise HTTPException(status_code=404, detail="AI SQL attempt was not found.")
        return [AiSqlAttemptEvent.model_validate(event) for event in list_attempt_events(attempt_id, limit)]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/admin/ai-sql-attempts/{attempt_id}/review", response_model=AiSqlAttempt)
def admin_review_ai_sql_attempt(
    attempt_id: str,
    review: AiSqlAttemptReviewRequest,
    authorization: str | None = Header(default=None),
) -> AiSqlAttempt:
    _require_super_admin_auth(authorization)
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
    authorization: str | None = Header(default=None),
) -> AiSqlAttemptPreview:
    _require_super_admin_auth(authorization)
    try:
        return AiSqlAttemptPreview.model_validate(preview_attempt_rows(attempt_id, limit))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/sql-mistake-examples", response_model=list[SqlMistakeExample])
def admin_sql_mistake_examples(
    limit: int = Query(default=100, ge=1, le=200),
    authorization: str | None = Header(default=None),
) -> list[SqlMistakeExample]:
    _require_super_admin_auth(authorization)
    try:
        return [SqlMistakeExample.model_validate(item) for item in list_mistake_examples(limit)]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/sql-mistake-groups", response_model=list[SqlMistakeGroup])
def admin_sql_mistake_groups(
    limit: int = Query(default=100, ge=1, le=200),
    authorization: str | None = Header(default=None),
) -> list[SqlMistakeGroup]:
    _require_super_admin_auth(authorization)
    try:
        return [SqlMistakeGroup.model_validate(item) for item in list_mistake_groups(limit)]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.patch("/api/admin/sql-mistake-examples/{mistake_id}/context", response_model=SqlMistakeExample)
def admin_update_sql_mistake_context_usage(
    mistake_id: str,
    payload: SqlMistakeContextUsageRequest,
    authorization: str | None = Header(default=None),
) -> SqlMistakeExample:
    _require_super_admin_auth(authorization)
    try:
        return SqlMistakeExample.model_validate(set_mistake_context_usage(mistake_id, payload.use_in_context))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.patch("/api/admin/sql-mistake-groups/{group_key}/context", response_model=SqlMistakeGroup)
def admin_update_sql_mistake_group_context_usage(
    group_key: str,
    payload: SqlMistakeContextUsageRequest,
    authorization: str | None = Header(default=None),
) -> SqlMistakeGroup:
    _require_super_admin_auth(authorization)
    try:
        return SqlMistakeGroup.model_validate(set_mistake_group_context_usage(group_key, payload.use_in_context))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
