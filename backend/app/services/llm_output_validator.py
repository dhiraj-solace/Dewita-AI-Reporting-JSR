import json
import logging
import re
from typing import Any

import httpx
from pydantic import ValidationError

from app.core.config import get_settings
from app.models import ValidationResult
from app.services.schema_validator import extract_cte_names

logger = logging.getLogger(__name__)

VALIDATION_SYSTEM_PROMPT = """
You are the Judge LLM for an AI reporting backend.
Validate whether LLM-1's SQL is schema-correct, safe, and semantically aligned with the user's report request.

Rules:
- Return strict JSON only. No markdown, no comments, no prose outside JSON.
- Do not include hidden chain-of-thought or internal reasoning.
- Be strict about SQL safety and schema correctness.
- SQL must be read-only SELECT/CTE only.
- Reject unsafe SQL operations: INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, GRANT, REVOKE, CALL, EXECUTE, MERGE.
- Check table names, column names against the provided database_schema only.
- Do not forgive column or table names that only sound plausible; they must exist in database_schema.
- Never override deterministic_validation. If it reports a failure, reject the SQL using that exact root cause.
- After identifiers pass, judge whether joins, filters, date ranges, grouping, aggregation, ordering,
  and selected business metrics correctly answer the user_question.
- Treat aliases and CTE names as SQL-local names, not physical schema tables.

LIMIT RULES (read carefully):
- ONLY check or enforce a LIMIT if the user explicitly used one of these phrases in their query:
    "top N", "first N", "last N", "bottom N", "limit N", "only N", "single record", "one record"
  where N is a specific number.
- If the user did NOT use any of those phrases, the SQL may include any LIMIT (e.g. a safety cap
  like LIMIT 100, LIMIT 500) or no LIMIT at all. Do NOT flag it. Do NOT mention LIMIT in the reason.
- Never infer a top-N or limit requirement from the SQL itself.
  The requirement must come from the user's own words only.
- If the user DID ask for top/first/last/bottom N, the SQL LIMIT must match that exact N.
- LIMIT check examples:
    - User says "top 10 projects"    → SQL has LIMIT 10  : VALID
    - User says "first 5 employees"  → SQL has LIMIT 5   : VALID
    - User says "only one record"    → SQL has LIMIT 1   : VALID
    - User says "top 10 projects"    → SQL has LIMIT 500 : INVALID (500 ≠ 10)
    - User says "top 10 projects"    → SQL has LIMIT 20  : INVALID (20 ≠ 10)
    - User says "top 10 projects"    → SQL has no LIMIT  : INVALID (LIMIT 10 required)
    - User says "show me a summary"  → SQL has LIMIT 100 : VALID (no top-N requested, safety cap is fine)
    - User says "show me a summary"  → SQL has no LIMIT  : VALID (no top-N requested)
- The SQL may be multi-line. Always inspect the full SQL including the final line before
  making any judgment about LIMIT.
- Never say "User requested top N but SQL LIMIT is missing" unless the words
  top / first / last / bottom / limit N appear explicitly in the user query.

SCHEMA RULES:
- Every table name and column name used in the SQL must exist in database_schema.
- Do not accept names that merely sound plausible or are close matches.
- If a name is not found in database_schema, mark as invalid and name the missing identifier.

SAFETY RULES:
- Reject any SQL containing: INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE,
  CREATE, GRANT, REVOKE, CALL, EXECUTE, MERGE.
- Only SELECT statements and CTEs (WITH ... SELECT) are allowed.

OUTPUT RULES:
- If valid, return exactly:
  {"is_valid": true, "reason": "", "error_type": "", "validation_stage": "judge",
   "fix_hint": "", "retryable": false, "missing_table": null, "missing_column": null}
- If invalid, return the same shape with one clear root cause.
- The reason must describe only one issue. Do not list multiple issues.
- Do not mention LIMIT in the reason unless the user explicitly requested a specific top/bottom/first/last N.
- error_type must be one of: invalid_table, invalid_column, wrong_join, wrong_filter,
  wrong_aggregation, wrong_ordering, wrong_date_range, unsafe_query, limit_mismatch,
  permission_denied, unclear_question, unknown.
- validation_stage must be "schema", "safety", or "judge".
- missing_table and missing_column must be null unless that exact identifier is missing.
- fix_hint must be a concrete correction instruction for LLM-1.
- retryable should be false only when the user question needs clarification.

Required JSON shape:
{
  "is_valid": true,
  "reason": "",
  "error_type": "",
  "validation_stage": "judge",
  "fix_hint": "",
  "retryable": false,
  "missing_table": null,
  "missing_column": null
}
""".strip()

class OutputValidationError(Exception):
    pass


async def validate_llm_report_output(
    *,
    question: str,
    schema: dict[str, Any],
    generated_sql: str,
    report_category: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    current_user_role: str | None = None,
    deterministic_validation: dict[str, Any] | None = None,
) -> ValidationResult:
    settings = get_settings()
    if not settings.llm_validator_enabled:
        return ValidationResult(is_valid=True, errors=[], retry_prompt="")
    
    payload = build_validation_payload(
        question=question,
        schema=schema,
        generated_sql=generated_sql,
        report_category=report_category,
        start_date=start_date,
        end_date=end_date,
        current_user_role=current_user_role,
        deterministic_validation=deterministic_validation,
    )
    messages = [
        {"role": "system", "content": VALIDATION_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    provider = settings.llm_validator_provider.strip().lower()
    if provider == "openrouter":
        if not settings.openrouter_api_key:
            raise OutputValidationError("OpenRouter Judge is enabled but OPENROUTER_API_KEY is missing.")
        url = "https://openrouter.ai/api/v1/chat/completions"
        body = {
            "model": settings.llm_validator_openrouter_model or settings.openrouter_model,
            "temperature": 0,
            "max_tokens": 300,
            "response_format": {"type": "json_object"},
            "messages": messages,
        }
        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        if settings.openrouter_site_url:
            headers["HTTP-Referer"] = settings.openrouter_site_url
        if settings.openrouter_app_name:
            headers["X-Title"] = settings.openrouter_app_name
    else:
        url = settings.llm_validator_url
        body = {
            "model": settings.llm_validator_model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0, "top_p": 1, "top_k": 1, "num_predict": 300, "num_ctx": 8192},
            "messages": messages,
        }
        headers = {}
    
    try:
        timeout = httpx.Timeout(settings.llm_validator_timeout_seconds, connect=10)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=body, headers=headers)
            response.raise_for_status()
        response_payload = response.json()
        if provider == "openrouter":
            content = response_payload.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        else:
            content = response_payload.get("message", {}).get("content", "{}")
        return _parse_validation_result(content)
    except httpx.HTTPError as exc:
        message = _http_error_message(exc)
        logger.warning("Local LLM validator request failed: %s", message)
        raise OutputValidationError(f"Local LLM validator request failed: {message}") from exc
    except (json.JSONDecodeError, ValidationError, KeyError, TypeError) as exc:
        logger.warning("Local LLM validator returned an invalid response.")
        raise OutputValidationError("Local LLM validator returned an invalid response.") from exc


def build_validation_payload(
    *,
    question: str,
    schema: dict[str, Any],
    generated_sql: str,
    report_category: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    current_user_role: str | None = None,
    deterministic_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "user_question": question,
        "report_category": report_category,
        "requested_date_range": {"start_date": start_date, "end_date": end_date},
        "current_user_role": current_user_role,
        "deterministic_validation": deterministic_validation or {"is_valid": True},
        "database_schema": _compact_schema(schema, generated_sql),
        "llm_1_generated_sql": generated_sql,
    }

def _parse_validation_result(content: str) -> ValidationResult:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = json.loads(_extract_json_object(content))

    if not isinstance(parsed, dict):
        raise TypeError("Validator response must be a JSON object.")
    if "reason" not in parsed:
        parsed["reason"] = _reason_from_errors(parsed.get("errors"))
    parsed.setdefault("error_type", "")
    parsed.setdefault("validation_stage", "judge")
    parsed.setdefault("fix_hint", "")
    parsed.setdefault("retryable", not bool(parsed.get("is_valid")))
    parsed.setdefault("missing_table", None)
    parsed.setdefault("missing_column", None)
    parsed.setdefault("errors", [])
    parsed.setdefault("retry_prompt", "")
    return ValidationResult.model_validate(parsed)


def _reason_from_errors(errors: Any) -> str:
    if isinstance(errors, list) and errors:
        first = errors[0]
        if isinstance(first, dict):
            return str(first.get("message") or first.get("fix_hint") or "")
    return ""


def _compact_schema(schema: dict[str, Any], sql: str) -> dict[str, Any]:
    table_names: list[str] = []
    tables_by_name: dict[str, dict[str, Any]] = {}
    for table in schema.get("tables", []) if isinstance(schema, dict) else []:
        if not isinstance(table, dict) or not table.get("name"):
            continue
        table_name = table["name"]
        table_names.append(table_name)
        tables_by_name[table_name.lower()] = table
        for alias in table.get("aliases", []) or []:
            if isinstance(alias, str):
                tables_by_name[alias.lower()] = table
    
    referenced_names = _referenced_table_names(sql, tables_by_name)
    compact_tables: list[dict[str, Any]] = []
    for table_name in sorted(referenced_names):
        table = tables_by_name.get(table_name.lower())
        if not table:
            compact_tables.append({"name": table_name, "missing_from_schema": True, "columns": []})
            continue
        columns = []
        for column in table.get("columns", []) or []:
            if not isinstance(column, dict) or not column.get("name"):
                continue
            columns.append(
                {
                    "name": column["name"],
                    "type": column.get("type") or column.get("data_type"),
                }
            )
        compact_tables.append(
            {
                "name": table["name"],
                "aliases": table.get("aliases", []) or [],
                "columns": columns,
            }
        )

    return {
        "all_table_names": sorted(set(table_names)),
        "referenced_tables": compact_tables,
        "relationships": _relationships_for_tables(schema, referenced_names),
    }


def _referenced_table_names(sql: str, tables_by_name: dict[str, dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    cte_names = extract_cte_names(sql)
    for match in re.finditer(r"\b(?:from|join)\s+`?([A-Za-z_][\w]*)`?", sql, re.IGNORECASE):
        raw_name = match.group(1)
        if raw_name.lower() in cte_names:
            continue
        table = tables_by_name.get(raw_name.lower())
        names.add(table["name"] if table else raw_name)
    return names


def _relationships_for_tables(schema: dict[str, Any], table_names: set[str]) -> list[dict[str, Any]]:
    if not isinstance(schema, dict):
        return []
    lowered = {name.lower() for name in table_names}
    relationships = []
    for relationship in schema.get("relationships", []) or []:
        if not isinstance(relationship, dict):
            continue
        left = str(relationship.get("from", "")).split(".", 1)[0].lower()
        right = str(relationship.get("to", "")).split(".", 1)[0].lower()
        if left in lowered or right in lowered:
            relationships.append(relationship)
    return relationships


def _http_error_message(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "timed out waiting for local Qwen validator response"
    if isinstance(exc, httpx.ConnectError):
        return "could not connect to local validator endpoint"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"validator endpoint returned HTTP {exc.response.status_code}"
    return exc.__class__.__name__


def _extract_json_object(content: str) -> str:
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise json.JSONDecodeError("No JSON object found", content, 0)
    return content[start : end + 1]
