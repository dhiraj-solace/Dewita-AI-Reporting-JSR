from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.db import get_engine
from app.models import AiSqlAttempt, AiSqlAttemptReviewRequest, GeneratedReport, ReportRequest
from app.services.catalog import load_report_catalog, load_schema_catalog
from app.services.ai_sql_attempt_store import get_attempt, list_attempts, review_attempt
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
                settings.openrouter_api_key
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


@app.post("/api/reports/query", response_model=GeneratedReport)
async def query_report(request: ReportRequest) -> GeneratedReport:
    try:
        return await build_report(request)
    except ReportBuildError as exc:
        raise HTTPException(
            status_code=400,
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


