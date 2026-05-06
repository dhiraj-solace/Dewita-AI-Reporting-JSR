import json
import logging
import re
import sys
from datetime import datetime
from time import perf_counter
from typing import Any
from app.core.config import get_settings
from app.db import fetch_rows
from app.models import GeneratedReport, ReportRequest, RetryAttempt
from app.services.ai_sql_attempt_store import create_attempt, similar_gold_examples, update_attempt
from app.services.date_resolver import resolve_date_range
from app.services.llm import (
    AiSqlGenerationError,
    build_sql_generation_payload_preview,
    generate_sql_repair_with_ai,
    generate_sql_validation_retry_with_ai,
    generate_sql_with_ai,
)
from app.services.llm_output_validator import (
    OutputValidationError,
    build_validation_payload,
    validate_llm_report_output,
)
from app.services.schema_service import schema_service
from app.services.schema_validator import (
    SchemaDiagnosis,
    SchemaValidationError,
    diagnose_database_error,
    validate_sql_against_schema,
)
from app.services.sql_guard import normalize_live_schema_sql, validate_select_sql
from app.services.sql_mistake_store import (
    create_mistake_example,
    similar_mistake_examples,
    update_attempt_mistakes_with_final_sql,
)
from app.services.sql_safety_validator import SafetyValidationResult, validate_sql_safety
from app.services.templates import find_template

logger = logging.getLogger(__name__)

VALIDATION_FALLBACK_MESSAGE = (
    "ERROR: Unable to generate a valid SQL query after multiple attempts. Please refine your query."
)


class ReportBuildError(Exception):
    def __init__(
        self,
        message: str,
        attempts: list[RetryAttempt],
        title: str = "Unable to build report",
        solution: str | None = None,
        status_code: int | None = None,
        attempt_id: str | None = None,
    ):
        super().__init__(message)
        self.attempts = attempts
        self.title = title
        self.solution = solution
        self.status_code = status_code
        self.attempt_id = attempt_id


async def build_report(request: ReportRequest) -> GeneratedReport:
    warnings: list[str] = []
    retry_attempts: list[RetryAttempt] = []
    resolved_dates = resolve_date_range(request.question, request.start_date, request.end_date)
    schema_snapshot = _safe_schema()
    attempt_id = create_attempt(request.question, schema_snapshot)
    _console_attempt_log(attempt_id, "request", f"received user question: {_short_reason(request.question)}")
    _console_attempt_log(attempt_id, "schema", f"loaded schema with {_schema_table_count(schema_snapshot)} table(s)")
    _console_attempt_log(attempt_id, "start", "request started")
    _console_validation_log("request started")
    _console_validation_detail("user query", {"question": request.question, "limit": request.limit, "dry_run": request.dry_run})
    try:
        _console_attempt_log(attempt_id, "examples", "searching previous gold examples")
        example_search_started = perf_counter()
        examples, example_source = similar_gold_examples(request.question, limit=3, attempt_id=attempt_id)
        mistake_examples = similar_mistake_examples(request.question, limit=3)
        example_elapsed_ms = int((perf_counter() - example_search_started) * 1000)
        if example_source == "vector":
            _console_attempt_log(attempt_id, "examples", "vector DB search returned approved examples")
        else:
            _console_attempt_log(attempt_id, "examples", "vector DB unavailable or empty; using keyword/token similarity")
        _console_attempt_detail(
            attempt_id,
            "examples",
            {
                "source": example_source,
                "elapsed_ms": example_elapsed_ms,
                "count": len(examples),
                "examples": examples,
                "mistakes_count": len(mistake_examples),
                "mistakes": mistake_examples,
            },
        )
        _console_attempt_detail(
            attempt_id,
            "llm1-input",
            build_sql_generation_payload_preview(
                request.question,
                resolved_dates.start_date,
                resolved_dates.end_date,
                examples,
                mistake_examples,
            ),
        )
        _console_attempt_log(attempt_id, "generation", "calling first AI model")
        generated = await generate_sql_with_ai(
            request.question,
            resolved_dates.start_date,
            resolved_dates.end_date,
            examples,
            mistake_examples,
        )
    except AiSqlGenerationError as exc:
        update_attempt(attempt_id, execution_status="failed", execution_error=str(exc))
        _console_attempt_log(attempt_id, "generation", f"failed: {_short_reason(str(exc))}")
        error = _ai_report_error(exc, [])
        error.attempt_id = attempt_id
        raise error from exc

    if generated is None:
        logger.warning("AI SQL generation failed.")
        logger.info("Falling back to template-based report generation")
        
        template = find_template(request.question)
        if template is None:
            logger.warning("No exact template match found, using Project Summary as default")
            template = find_template("project summary")
            warnings.append("No exact report template matched; using Project Summary Report as a safe fallback.")
        else:
            logger.info("Using matched report template.")
            
        generated = {
            "title": template.title,
            "sql": template.sql,
            "explanation": template.explanation,
        }
        warnings.append(
            "AI SQL generation was unavailable or rejected by the provider, so a safe built-in template was used."
        )
        _console_validation_log("template output 1 generated")
        _console_validation_detail("template output 1", generated)
        update_attempt(attempt_id, generated_sql=generated.get("sql"))
        _console_attempt_log(attempt_id, "generation", "SQL generated from template fallback")
        _console_attempt_detail(attempt_id, "generation", {"source": "template", "generated_sql": generated.get("sql")})
    else:
        logger.info("AI SQL generation successful.")
        _console_validation_log("llm1 output 1 generated")
        _console_validation_detail("llm1 output 1", generated)
        update_attempt(attempt_id, generated_sql=generated.get("sql"))
        _console_attempt_log(attempt_id, "generation", "SQL generated by first AI model")
        _console_attempt_detail(attempt_id, "generation", {"source": "ai", "generated_sql": generated.get("sql")})

    try:
        generated, sql = await _validate_generated_output_with_retries(
            generated,
            request,
            resolved_dates.start_date,
            resolved_dates.end_date,
            warnings,
            retry_attempts,
            attempt_id,
        )
    except ReportBuildError as exc:
        update_attempt(attempt_id, execution_status="failed", execution_error=str(exc))
        exc.attempt_id = attempt_id
        raise
    params = {"start_date": resolved_dates.start_date, "end_date": resolved_dates.end_date}

    columns: list[str] = []
    rows: list[dict] = []
    if not request.dry_run:
        _console_validation_log("validation passed; executing SQL now")
        _console_validation_detail("sql execution request", {"sql": sql, "params": params})
        _console_attempt_log(attempt_id, "execution", "executing final SQL")
        _console_attempt_log(attempt_id, "execution", "SQL execution started")
        _console_attempt_detail(attempt_id, "execution", {"final_sql": sql, "params": params})
        try:
            execution_started = perf_counter()
            columns, rows = fetch_rows(sql, params)
            execution_elapsed_ms = int((perf_counter() - execution_started) * 1000)
            retry_attempts.append(
                RetryAttempt(
                    attempt=len(retry_attempts) + 1,
                    status="success",
                    message="Validated SQL executed successfully.",
                    sql=sql,
                )
            )
            _console_validation_detail(
                "sql execution output",
                _execution_summary(columns, len(rows)),
            )
            update_attempt(
                attempt_id,
                final_sql=sql,
                execution_status="success",
                execution_error=None,
                result_row_count=len(rows),
            )
            update_attempt_mistakes_with_final_sql(attempt_id, sql)
            _console_attempt_detail(
                attempt_id,
                "execution",
                {"status": "success", "row_count": len(rows)},
            )
            _console_attempt_log(
                attempt_id,
                "execution",
                f"SQL execution completed row_count={len(rows)} elapsed_ms={execution_elapsed_ms}",
            )
        except Exception as exc:
            _console_validation_detail("sql execution error", {"error": str(exc)})
            update_attempt(
                attempt_id,
                final_sql=sql,
                execution_status="failed",
                execution_error=str(exc),
                result_row_count=0,
            )
            _console_attempt_log(attempt_id, "execution", f"failed: {_short_reason(str(exc))}")
            _console_attempt_log(attempt_id, "execution", f"execution error: {_short_reason(str(exc))}")
            raise ReportBuildError(str(exc), retry_attempts, title="SQL execution failed", attempt_id=attempt_id) from exc
    else:
        _console_validation_log("validation passed; dry run skips SQL execution")
        _validate_with_current_schema(sql, retry_attempts, warnings)
        update_attempt_mistakes_with_final_sql(attempt_id, sql)
        update_attempt(
            attempt_id,
            final_sql=sql,
            execution_status="dry_run",
            execution_error=None,
            result_row_count=0,
        )
        _console_attempt_log(attempt_id, "execution", "dry run skipped SQL execution")

    return GeneratedReport(
        attempt_id=attempt_id,
        title=generated.get("title") or "SQL Report",
        question=request.question,
        sql=sql,
        explanation=generated.get("explanation") or "",
        assumptions=[],
        columns=columns,
        rows=rows,
        row_count=len(rows),
        dry_run=request.dry_run,
        warnings=warnings,
        retry_attempts=retry_attempts,
    )


async def _validate_generated_output_with_retries(
    generated: dict,
    request: ReportRequest,
    start_date: str | None,
    end_date: str | None,
    warnings: list[str],
    retry_attempts: list[RetryAttempt],
    attempt_id: str,
) -> tuple[dict, str]:
    settings = get_settings()
    max_retries = min(2, max(1, settings.llm_validator_max_retries))
    max_rows = min(request.limit, settings.max_rows)
    requested_result_limit = _requested_result_limit(request.question)
    sql_limit = min(max_rows, requested_result_limit) if requested_result_limit else max_rows
    current = dict(generated)
    last_error_message = "Generated report output did not pass validation."
    llm1_outputs = 1
    llm2_calls = 0

    for attempt in range(1, max_retries + 1):
        validation_errors: list[dict] = []
        retry_prompt = ""
        prepared_sql: str | None = None
        schema = _safe_schema()
        mistake_saved = False

        _console_validation_log(f"validator attempt {attempt} started for output {llm1_outputs}")
        _console_attempt_log(attempt_id, "validator", f"attempt {attempt} started for output {llm1_outputs}")
        try:
            raw_sql = current["sql"]
            prepared_sql = _prepare_sql(raw_sql, sql_limit, warnings, start_date, end_date)
            safety = validate_sql_safety(prepared_sql, schema)
            if not safety.isValid:
                _save_mistake(attempt_id, request.question, prepared_sql, safety)
                mistake_saved = True
                raise ValueError(safety.reason)
            _validate_requested_limit_alignment(prepared_sql, requested_result_limit)
        except SchemaValidationError as exc:
            last_error_message = exc.diagnosis.message
            _save_mistake(
                attempt_id,
                request.question,
                prepared_sql or current.get("sql", ""),
                SafetyValidationResult(False, last_error_message, "Use only schema tables and columns.", "medium", "invalid_column" if exc.diagnosis.column else "invalid_table"),
            )
            update_attempt(attempt_id, validator_status="failed", validator_feedback=last_error_message)
            _console_attempt_log(attempt_id, "validator", f"schema failed: {_short_reason(last_error_message)}")
            _console_validation_log(
                f"llm2 validation call {attempt} skipped qwen: {_short_reason(last_error_message)}"
            )
            validation_errors = [
                {
                    "type": "schema_error",
                    "message": exc.diagnosis.message,
                    "fix_hint": "Use only tables and columns from the provided schema.",
                }
            ]
            retry_prompt = exc.diagnosis.message
        except Exception as exc:
            last_error_message = str(exc)
            if not mistake_saved and (prepared_sql or current.get("sql")):
                _save_mistake(
                    attempt_id,
                    request.question,
                    prepared_sql or current.get("sql", ""),
                    SafetyValidationResult(False, last_error_message, "Regenerate a safe SQL query.", "medium", _mistake_type_from_reason(last_error_message)),
                )
            update_attempt(attempt_id, validator_status="failed", validator_feedback=last_error_message)
            _console_attempt_log(attempt_id, "validator", f"safety failed: {_short_reason(last_error_message)}")
            _console_validation_log(
                f"llm2 validation call {attempt} skipped qwen: {_short_reason(last_error_message)}"
            )
            validation_errors = [
                {
                    "type": "safety_error",
                    "message": str(exc),
                    "fix_hint": "Return one safe read-only SELECT query that matches the report request.",
                }
            ]
            retry_prompt = str(exc)
        else:
            try:
                llm2_calls += 1
                _console_validation_log(f"llm2 qwen call {llm2_calls} started for output {llm1_outputs}")
                validation_payload = build_validation_payload(
                    question=request.question,
                    schema=schema,
                    generated_sql=prepared_sql,
                )
                _console_validation_detail(
                    "llm2 validation request",
                    _validation_payload_for_console(validation_payload),
                )
                validation = await validate_llm_report_output(
                    question=request.question,
                    schema=schema,
                    generated_sql=prepared_sql,
                )
                _console_validation_detail("llm2 validation response", validation.model_dump())
                _console_attempt_detail(attempt_id, "validator", validation.model_dump())
            except OutputValidationError as exc:
                update_attempt(attempt_id, validator_status="failed", validator_feedback=str(exc))
                retry_attempts.append(
                    _validator_attempt(attempt, "failed", _short_reason(str(exc)))
                )
                logger.warning("Validator attempt %s failed: %s", attempt, _short_reason(str(exc)))
                _console_validation_log(
                    f"llm2 qwen call {llm2_calls} failed: {_short_reason(str(exc))}"
                )
                raise ReportBuildError(
                    "Local LLM validator request failed.",
                    retry_attempts,
                    title="Report validator unavailable",
                    solution=(
                        "Ensure Ollama is running with qwen2.5:3b and increase "
                        "LLM_VALIDATOR_TIMEOUT_SECONDS if local validation takes longer."
                    ),
                ) from exc
            else:
                if validation.is_valid:
                    update_attempt(
                        attempt_id,
                        validator_status="success",
                        validator_feedback=validation.reason or f"Validator accepted output on attempt {attempt}.",
                        final_sql=prepared_sql,
                    )
                    retry_attempts.append(
                        _validator_attempt(attempt, "success", f"Validator accepted output on attempt {attempt}.")
                    )
                    logger.info("Validator accepted output on attempt %s.", attempt)
                    _console_validation_log(
                        f"success llm1_outputs={llm1_outputs} llm2_calls={llm2_calls} passed_on_attempt={attempt}"
                    )
                    _console_attempt_log(attempt_id, "validator", "validator result success")
                    _console_attempt_log(attempt_id, "final-sql", "final SQL accepted")
                    _console_attempt_log(attempt_id, "validator", f"success on attempt {attempt}")
                    return current, prepared_sql
                if _is_limit_false_positive(validation.reason, prepared_sql, requested_result_limit):
                    update_attempt(
                        attempt_id,
                        validator_status="success",
                        validator_feedback="Backend overrode validator LIMIT false positive; SQL LIMIT matches user request.",
                        final_sql=prepared_sql,
                    )
                    retry_attempts.append(
                        _validator_attempt(
                            attempt,
                            "success",
                            "Backend overrode validator LIMIT false positive; SQL LIMIT matches user request.",
                        )
                    )
                    _console_validation_detail(
                        "llm2 validation override",
                        {
                            "reason_from_llm2": validation.reason,
                            "backend_check": "requested LIMIT matches SQL LIMIT",
                            "decision": "accepted",
                        },
                    )
                    _console_attempt_log(attempt_id, "validator", "accepted after LIMIT false-positive override")
                    _console_attempt_log(attempt_id, "final-sql", "final SQL accepted")
                    return current, prepared_sql
                last_error_message = validation.reason or _validation_error_summary(
                    [error.model_dump() for error in validation.errors]
                )
                _save_mistake(
                    attempt_id,
                    request.question,
                    prepared_sql,
                    SafetyValidationResult(False, last_error_message, "Regenerate SQL using validator feedback.", "medium", _mistake_type_from_reason(last_error_message)),
                )
                update_attempt(attempt_id, validator_status="failed", validator_feedback=last_error_message)
                validation_errors = [
                    {
                        "type": "validation_error",
                        "message": last_error_message,
                        "fix_hint": "Regenerate only a corrected SQL query.",
                    }
                ]
                retry_prompt = last_error_message

        retry_attempts.append(_validator_attempt(attempt, "failed", last_error_message))
        logger.info("Validator attempt %s rejected output: %s", attempt, _short_reason(last_error_message))
        _console_validation_log(
            f"validator attempt {attempt} rejected output {llm1_outputs}: {_short_reason(last_error_message)}"
        )
        _console_attempt_log(
            attempt_id,
            "validator",
            f"attempt {attempt} rejected output {llm1_outputs}: {_short_reason(last_error_message)}",
        )

        if attempt >= max_retries:
            break

        _console_validation_log(f"llm1 retry {attempt + 1} started after validator rejection")
        _console_attempt_log(attempt_id, "retry", f"regeneration attempt {attempt + 1} started")
        llm1_retry_payload = {
            "user_query": request.question,
            "failed_sql": prepared_sql or current.get("sql", ""),
            "validation_reason_from_llm2": retry_prompt or last_error_message,
            "validation_errors": validation_errors,
            "start_date": start_date,
            "end_date": end_date,
        }
        _console_validation_detail("data passed to llm1 retry", llm1_retry_payload)
        try:
            regenerated = await generate_sql_validation_retry_with_ai(
                llm1_retry_payload["user_query"],
                llm1_retry_payload["start_date"],
                llm1_retry_payload["end_date"],
                {"sql": llm1_retry_payload["failed_sql"]},
                llm1_retry_payload["validation_errors"],
                llm1_retry_payload["validation_reason_from_llm2"],
            )
        except AiSqlGenerationError as exc:
            raise _ai_report_error(exc, []) from exc

        if regenerated is None:
            _console_validation_log(f"llm1 retry {attempt + 1} unavailable")
            _console_attempt_log(attempt_id, "retry", f"regeneration attempt {attempt + 1} unavailable")
            break
        current = regenerated
        llm1_outputs += 1
        _console_validation_log(f"llm1 output {llm1_outputs} generated")
        _console_validation_detail(f"llm1 output {llm1_outputs}", current)
        update_attempt(attempt_id, regenerated_sql=current.get("sql"))
        _console_attempt_log(attempt_id, "retry", "regenerated SQL received")
        _console_attempt_detail(attempt_id, "retry", {"regenerated_sql": current.get("sql")})

    _console_validation_log(f"failed llm1_outputs={llm1_outputs} llm2_calls={llm2_calls}")
    update_attempt(attempt_id, validator_status="failed", validator_feedback=last_error_message)
    _console_attempt_log(attempt_id, "validator", f"failed after retries: {_short_reason(last_error_message)}")
    raise ReportBuildError(
        VALIDATION_FALLBACK_MESSAGE,
        retry_attempts,
        title="Unable to build report",
        solution="Refine the report question or ask an admin to review the schema and local validator service.",
    )


def _structured_validator_output(generated: dict, sql: str) -> dict:
    return {
        "title": generated.get("title") or "Custom Report",
        "sql": sql,
        "explanation": generated.get("explanation") or "",
        "assumptions": generated.get("assumptions") or [],
    }


def _requested_result_limit(question: str) -> int | None:
    normalized = question.lower()
    digit_match = re.search(
        r"\b(?:top|bottom|first|last|limit|show)\s+(\d{1,4})\b",
        normalized,
        re.IGNORECASE,
    )
    if digit_match:
        value = int(digit_match.group(1))
        return value if value > 0 else None

    word_numbers = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
    }
    word_pattern = "|".join(word_numbers)
    word_match = re.search(
        rf"\b(?:top|bottom|first|last|limit|show|only)\s+({word_pattern})\b",
        normalized,
    )
    if word_match:
        return word_numbers[word_match.group(1)]

    if re.search(r"\b(?:only\s+1|single|one\s+record|one\s+row|one\s+result)\b", normalized):
        return 1

    return None


def _validate_requested_limit_alignment(sql: str, requested_limit: int | None) -> None:
    if requested_limit is None:
        return
    limit_match = re.search(r"\blimit\s+(\d+)\s*$", sql, re.IGNORECASE)
    if not limit_match:
        raise ValueError(f"The user requested {requested_limit} rows, but the SQL has no LIMIT clause.")
    sql_limit = int(limit_match.group(1))
    if sql_limit != requested_limit:
        raise ValueError(
            f"The user requested top {requested_limit} rows, but the SQL returns LIMIT {sql_limit}."
        )


def _is_limit_false_positive(reason: str, sql: str, requested_limit: int | None) -> bool:
    if requested_limit is None:
        return False
    normalized_reason = reason.lower()
    if "limit" not in normalized_reason:
        return False
    limit_match = re.search(r"\blimit\s+(\d+)\s*$", sql, re.IGNORECASE)
    return bool(limit_match and int(limit_match.group(1)) == requested_limit)


def _validation_error_summary(validation_errors: list[dict]) -> str:
    if not validation_errors:
        return "Validator rejected the generated output."
    first_error = validation_errors[0]
    error_type = str(first_error.get("type") or "validation_error").replace("_", " ")
    message = str(first_error.get("message") or "Generated output failed validation.")
    return _short_reason(f"{error_type}: {message}")


def _save_mistake(
    attempt_id: str,
    user_question: str,
    wrong_sql: str | None,
    safety: SafetyValidationResult,
) -> None:
    create_mistake_example(
        query_attempt_id=attempt_id,
        user_question=user_question,
        wrong_sql=wrong_sql,
        validator_feedback=safety.reason,
        validation_reason=safety.reason,
        mistake_type=safety.mistakeType,
        risk_level=safety.riskLevel,
        corrected_sql=safety.fixedSuggestion,
    )


def _mistake_type_from_reason(reason: str) -> str:
    lowered = reason.lower()
    if "table" in lowered and ("not present" in lowered or "does not exist" in lowered):
        return "invalid_table"
    if "column" in lowered:
        return "invalid_column"
    if "limit" in lowered:
        return "missing_limit"
    if "multiple" in lowered:
        return "multiple_statements"
    if "forbidden" in lowered or "dangerous" in lowered or "write" in lowered:
        return "dangerous_query"
    if "syntax" in lowered:
        return "syntax_error"
    if "permission" in lowered:
        return "permission_denied"
    if "unclear" in lowered or "clarification" in lowered:
        return "unclear_question"
    return "unknown"


def _validator_attempt(attempt: int, status: str, reason: str) -> RetryAttempt:
    return RetryAttempt(
        attempt=attempt,
        status=status,
        message=f"Validator {status}: {_short_reason(reason)}",
        sql=None,
        schema_issue=None,
    )


def _short_reason(reason: str, max_length: int = 140) -> str:
    normalized = " ".join(str(reason).split())
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 1].rstrip() + "."


def _console_validation_log(message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    sys.stderr.write(f"[validator {timestamp}] {message}\n")
    sys.stderr.flush()


def _console_attempt_log(attempt_id: str, step: str, message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    sys.stderr.write(f"[ai-sql {timestamp} attempt={attempt_id} step={step}] {message}\n")
    sys.stderr.flush()


def _console_validation_detail(label: str, payload: Any) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    sys.stderr.write(f"[validator {timestamp}] {label}:\n{rendered}\n")
    sys.stderr.flush()


def _console_attempt_detail(attempt_id: str, step: str, payload: Any) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    sys.stderr.write(f"[ai-sql {timestamp} attempt={attempt_id} step={step}]\n{rendered}\n")
    sys.stderr.flush()


def _validation_payload_for_console(payload: dict[str, Any]) -> dict[str, Any]:
    visible_payload = dict(payload)
    schema = visible_payload.pop("database_schema", None)
    if isinstance(schema, dict):
        visible_payload["database_schema"] = {
            "hidden_in_console": True,
            "table_count": len(schema.get("all_table_names", []) or []),
            "referenced_table_count": len(schema.get("referenced_tables", []) or []),
        }
    return visible_payload


def _schema_table_count(schema: dict[str, Any]) -> int:
    if isinstance(schema.get("all_table_names"), list):
        return len(schema.get("all_table_names") or [])
    if isinstance(schema.get("tables"), list):
        return len(schema.get("tables") or [])
    if isinstance(schema.get("tables"), dict):
        return len(schema.get("tables") or {})
    return 0


def _execution_summary(columns: list[str], row_count: int) -> dict[str, Any]:
    preview = columns[:8]
    hidden_count = max(len(columns) - len(preview), 0)
    return {
        "status": "executed",
        "row_count": row_count,
        "columns": preview + ([f"... {hidden_count} more"] if hidden_count else []),
    }


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
    return validate_select_sql(sql)


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
