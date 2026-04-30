import logging
import re
from app.core.config import get_settings
from app.db import fetch_rows
from app.models import GeneratedReport, ReportRequest, RetryAttempt
from app.services.date_resolver import resolve_date_range
from app.services.llm import AiSqlGenerationError, generate_sql_repair_with_ai, generate_sql_with_ai
from app.services.schema_service import schema_service
from app.services.schema_validator import (
    SchemaDiagnosis,
    SchemaValidationError,
    diagnose_database_error,
    validate_sql_against_schema,
)
from app.services.sql_guard import apply_limit, normalize_live_schema_sql, validate_select_sql
from app.services.templates import find_template

logger = logging.getLogger(__name__)


class ReportBuildError(Exception):
    def __init__(
        self,
        message: str,
        attempts: list[RetryAttempt],
        title: str = "Unable to build report",
        solution: str | None = None,
        status_code: int | None = None,
    ):
        super().__init__(message)
        self.attempts = attempts
        self.title = title
        self.solution = solution
        self.status_code = status_code


async def build_report(request: ReportRequest) -> GeneratedReport:
    warnings: list[str] = []
    resolved_dates = resolve_date_range(request.question, request.start_date, request.end_date)
    try:
        generated = await generate_sql_with_ai(request.question, resolved_dates.start_date, resolved_dates.end_date)
    except AiSqlGenerationError as exc:
        raise _ai_report_error(exc, []) from exc

    if generated is None:
        logger.warning(f"AI SQL generation failed for question: '{request.question}'")
        logger.info("Falling back to template-based report generation")
        
        template = find_template(request.question)
        if template is None:
            logger.warning("No exact template match found, using Project Summary as default")
            template = find_template("project summary")
            warnings.append("No exact report template matched; using Project Summary Report as a safe fallback.")
        else:
            logger.info(f"Using template: '{template.title}' for question: '{request.question}'")
            
        generated = {
            "title": template.title,
            "sql": template.sql,
            "explanation": template.explanation,
        }
        warnings.append(
            "AI SQL generation was unavailable or rejected by the provider, so a safe built-in template was used."
        )
    else:
        logger.info(f"AI SQL generation successful for question: '{request.question}'")

    sql = _prepare_sql(
        generated["sql"],
        min(request.limit, get_settings().max_rows),
        warnings,
        resolved_dates.start_date,
        resolved_dates.end_date,
    )
    params = {"start_date": resolved_dates.start_date, "end_date": resolved_dates.end_date}

    columns: list[str] = []
    rows: list[dict] = []
    retry_attempts: list[RetryAttempt] = []
    if not request.dry_run:
        columns, rows, sql = await _execute_with_schema_retries(sql, params, request, retry_attempts, warnings)
    else:
        _validate_with_current_schema(sql, retry_attempts, warnings)

    return GeneratedReport(
        title=generated["title"],
        question=request.question,
        sql=sql,
        explanation=generated["explanation"],
        assumptions=resolved_dates.assumptions + generated.get("assumptions", []),
        columns=columns,
        rows=rows,
        row_count=len(rows),
        dry_run=request.dry_run,
        warnings=warnings,
        retry_attempts=retry_attempts,
    )


def _prepare_sql(
    sql: str,
    limit: int,
    warnings: list[str],
    start_date: str | None,
    end_date: str | None,
) -> str:
    sql, normalization_warnings = normalize_live_schema_sql(sql)
    warnings.extend(normalization_warnings)
    sql = _render_terminal_sql(sql, {"start_date": start_date, "end_date": end_date})
    sql = validate_select_sql(sql)
    return apply_limit(sql, limit)


def _render_terminal_sql(sql: str, params: dict[str, str | None]) -> str:
    """Render named SQLAlchemy placeholders as MySQL literals for copy/paste use."""
    rendered = sql
    for name, value in params.items():
        escaped = value.replace("'", "''") if value is not None else None
        literal = "NULL" if escaped is None else f"'{escaped}'"
        rendered = re.sub(rf":{re.escape(name)}\b", literal, rendered)
    return rendered


def _validate_with_current_schema(
    sql: str,
    retry_attempts: list[RetryAttempt],
    warnings: list[str],
) -> None:
    try:
        schema = schema_service.get_schema()
        warnings.extend(validate_sql_against_schema(sql, schema))
        retry_attempts.append(
            RetryAttempt(attempt=1, status="success", message="Schema validation passed.", sql=sql)
        )
    except SchemaValidationError as exc:
        retry_attempts.append(_failed_attempt(1, "Schema validation failed.", sql, exc.diagnosis))
        raise ReportBuildError(exc.diagnosis.message, retry_attempts) from exc


async def _execute_with_schema_retries(
    sql: str,
    params: dict[str, str | None],
    request: ReportRequest,
    retry_attempts: list[RetryAttempt],
    warnings: list[str],
) -> tuple[list[str], list[dict], str]:
    max_rows = min(request.limit, get_settings().max_rows)
    current_sql = sql

    for attempt in (1, 2):
        try:
            schema = schema_service.get_schema(force_refresh=attempt > 1)
            warnings.extend(validate_sql_against_schema(current_sql, schema))
            columns, rows = fetch_rows(current_sql, params)
            retry_attempts.append(
                RetryAttempt(
                    attempt=attempt,
                    status="success",
                    message="Report query executed successfully.",
                    sql=current_sql,
                )
            )
            return columns, rows, current_sql
        except SchemaValidationError as exc:
            retry_attempts.append(_failed_attempt(attempt, "Schema validation failed.", current_sql, exc.diagnosis))
            if attempt == 1:
                try:
                    repaired_sql = await _repair_generated_sql(
                        request,
                        current_sql,
                        exc.diagnosis.message,
                        max_rows,
                        warnings,
                    )
                except AiSqlGenerationError as repair_exc:
                    raise _ai_report_error(repair_exc, retry_attempts) from repair_exc
                if repaired_sql:
                    current_sql = repaired_sql
                    warnings.append("Regenerated SQL using the schema validation error and retried it.")
                    continue
                warnings.append("AI SQL repair was unavailable, so a safe built-in template will be used.")
                break
            break
        except Exception as exc:
            diagnosis = diagnose_database_error(exc, _safe_schema())
            retry_message = diagnosis or SchemaDiagnosis(message=str(exc))
            retry_attempts.append(
                _failed_attempt(
                    attempt,
                    "Database rejected the generated SQL.",
                    current_sql,
                    retry_message,
                )
            )
            if attempt == 1:
                try:
                    repaired_sql = await _repair_generated_sql(
                        request,
                        current_sql,
                        retry_message.message,
                        max_rows,
                        warnings,
                    )
                except AiSqlGenerationError as repair_exc:
                    raise _ai_report_error(repair_exc, retry_attempts) from repair_exc
                if repaired_sql:
                    current_sql = repaired_sql
                    warnings.append("Regenerated SQL using the database error and retried it.")
                    continue
                warnings.append("AI SQL repair was unavailable, so a safe built-in template will be used.")
                break
            break

    fallback_sql = _fallback_sql(request, max_rows, warnings)
    try:
        schema = schema_service.get_schema(force_refresh=True)
        warnings.extend(validate_sql_against_schema(fallback_sql, schema))
        columns, rows = fetch_rows(fallback_sql, params)
        retry_attempts.append(
            RetryAttempt(
                attempt=3,
                status="success",
                message="Used a safe built-in template after generated SQL did not match the schema.",
                sql=fallback_sql,
            )
        )
        return columns, rows, fallback_sql
    except SchemaValidationError as exc:
        retry_attempts.append(_failed_attempt(3, "Fallback template failed schema validation.", fallback_sql, exc.diagnosis))
        raise ReportBuildError(exc.diagnosis.message, retry_attempts) from exc
    except Exception as exc:
        diagnosis = diagnose_database_error(exc, _safe_schema())
        retry_attempts.append(
            _failed_attempt(
                3,
                "Fallback template was rejected by the database.",
                fallback_sql,
                diagnosis or SchemaDiagnosis(message=str(exc)),
            )
        )
        raise ReportBuildError(str(exc), retry_attempts) from exc


def _fallback_sql(request: ReportRequest, max_rows: int, warnings: list[str]) -> str:
    template = find_template(request.question) or find_template("project summary")
    warnings.append("Generated SQL did not match the live schema, so a safe built-in template was retried.")
    resolved_dates = resolve_date_range(request.question, request.start_date, request.end_date)
    return _prepare_sql(template.sql, max_rows, warnings, resolved_dates.start_date, resolved_dates.end_date)


async def _repair_generated_sql(
    request: ReportRequest,
    failed_sql: str,
    error_message: str,
    max_rows: int,
    warnings: list[str],
) -> str | None:
    resolved_dates = resolve_date_range(request.question, request.start_date, request.end_date)
    repaired = await generate_sql_repair_with_ai(
        request.question,
        resolved_dates.start_date,
        resolved_dates.end_date,
        failed_sql,
        error_message,
    )
    if repaired is None:
        return None
    return _prepare_sql(repaired["sql"], max_rows, warnings, resolved_dates.start_date, resolved_dates.end_date)


def _safe_schema() -> dict:
    try:
        return schema_service.get_schema(force_refresh=False)
    except Exception:
        return {}


def _failed_attempt(
    attempt: int,
    message: str,
    sql: str,
    diagnosis: SchemaDiagnosis,
) -> RetryAttempt:
    return RetryAttempt(
        attempt=attempt,
        status="failed",
        message=message,
        sql=sql,
        schema_issue=diagnosis.message,
    )


def _ai_report_error(exc: AiSqlGenerationError, attempts: list[RetryAttempt]) -> ReportBuildError:
    return ReportBuildError(
        str(exc),
        attempts,
        title=exc.title,
        solution=exc.solution,
        status_code=exc.status_code,
    )
