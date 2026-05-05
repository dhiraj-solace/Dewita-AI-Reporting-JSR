import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from app.core.config import get_settings
from app.models import ReportEvaluation, RetryAttempt
from app.services.schema_service import schema_service

logger = logging.getLogger(__name__)
EVAL_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
EVAL_QUEUE_PATH = EVAL_DATA_DIR / "report_eval_queue.jsonl"
EVAL_BATCH_DIR = EVAL_DATA_DIR / "eval_batches"
EVAL_RESULTS_PATH = EVAL_DATA_DIR / "report_eval_results.jsonl"


class ReportEvaluationError(Exception):
    pass


async def evaluate_report_output(
    *,
    question: str,
    title: str,
    sql: str,
    explanation: str,
    assumptions: list[str],
    columns: list[str],
    rows: list[dict[str, Any]],
    row_count: int,
    dry_run: bool,
    warnings: list[str],
    retry_attempts: list[RetryAttempt],
) -> ReportEvaluation | None:
    settings = get_settings()
    if not settings.eval_enabled:
        return None

    if settings.eval_provider.lower() != "ollama":
        raise ReportEvaluationError(f"Unsupported eval provider: {settings.eval_provider}")

    schema = _safe_schema_summary()
    payload = {
        "question": question,
        "report": {
            "title": title,
            "sql": sql,
            "explanation": explanation,
            "assumptions": assumptions,
            "columns": columns,
            "sample_rows": rows[:5],
            "row_count": row_count,
            "dry_run": dry_run,
            "warnings": warnings,
        },
        "backend_validation": {
            "schema_available": bool(schema["tables"]),
            "schema_source": schema["source"],
            "schema_fetched_at": schema["fetched_at"],
            "table_count": schema["table_count"],
            "column_count": schema["column_count"],
            "retry_attempts": [attempt.model_dump() for attempt in retry_attempts],
            "sql_executed": (not dry_run) and any(
                attempt.status == "success" for attempt in retry_attempts
            ),
        },
        "schema_summary": schema,
    }
    if settings.eval_mode.lower() == "batch":
        try:
            await queue_report_evaluation(payload, settings.eval_batch_size)
        except Exception as exc:
            raise ReportEvaluationError(f"Could not queue report eval: {exc}") from exc
        return None

    return await _evaluate_with_ollama(
        payload,
        settings.ollama_base_url,
        settings.ollama_eval_model,
        settings.ollama_eval_timeout_seconds,
    )


async def queue_report_evaluation(payload: dict[str, Any], batch_size: int) -> None:
    record = _build_eval_record(payload)
    EVAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with EVAL_QUEUE_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    records = _read_jsonl(EVAL_QUEUE_PATH)
    effective_batch_size = max(batch_size, 10)
    pending = [item for item in records if item.get("eval_status") == "pending"]
    if len(pending) < effective_batch_size:
        return

    batch_id = f"eval_batch_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
    batch_ids = {item["id"] for item in pending[:effective_batch_size]}
    marked_records = []
    for item in records:
        if item.get("id") in batch_ids:
            marked = {
                **item,
                "eval_status": "evaluating",
                "eval_batch_id": batch_id,
                "eval_started_at": datetime.now(UTC).isoformat(),
            }
            marked_records.append(marked)
        else:
            marked_records.append(item)
    _write_jsonl(EVAL_QUEUE_PATH, marked_records)
    batch = [item for item in marked_records if item.get("id") in batch_ids]
    asyncio.create_task(_evaluate_batch(batch_id, batch))


async def evaluate_queued_reports(
    limit: int = 1,
    retry_failed: bool = False,
    reevaluate: bool = False,
) -> dict[str, Any]:
    records = _read_jsonl(EVAL_QUEUE_PATH)
    statuses = {"pending"}
    if retry_failed:
        statuses.add("eval_failed")
    if reevaluate:
        statuses.add("evaluated")
    candidates = [item for item in records if item.get("eval_status") in statuses]
    if not candidates:
        return {
            "status": "empty",
            "message": "No queued report evaluations matched the requested status.",
            "pending_count": sum(1 for item in records if item.get("eval_status") == "pending"),
            "failed_count": sum(1 for item in records if item.get("eval_status") == "eval_failed"),
            "evaluated_count": sum(1 for item in records if item.get("eval_status") == "evaluated"),
        }

    batch_id = f"manual_eval_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
    selected_ids = {item["id"] for item in candidates[: max(1, limit)]}
    marked_records = []
    for item in records:
        if item.get("id") in selected_ids:
            marked_records.append(
                {
                    **item,
                    "eval_status": "evaluating",
                    "eval_batch_id": batch_id,
                    "eval_started_at": datetime.now(UTC).isoformat(),
                    "eval_finished_at": None,
                    "eval_result": None,
                }
            )
        else:
            marked_records.append(item)
    _write_jsonl(EVAL_QUEUE_PATH, marked_records)
    batch = [item for item in marked_records if item.get("id") in selected_ids]
    result_record = await _evaluate_batch(batch_id, batch)
    return {
        "status": "completed",
        "evaluated_count": len(batch),
        "selected_ids": list(selected_ids),
        **result_record,
    }


async def _evaluate_batch(batch_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    settings = get_settings()
    batch_file = EVAL_BATCH_DIR / f"{batch_id}.json"
    EVAL_BATCH_DIR.mkdir(parents=True, exist_ok=True)
    batch_payload = {
        "batch_id": batch_id,
        "created_at": datetime.now(UTC).isoformat(),
        "record_count": len(records),
        "records": [_compact_eval_record_for_model(record) for record in records],
    }
    batch_file.write_text(json.dumps(batch_payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    try:
        result = await _evaluate_batch_with_ollama(
            batch_payload,
            settings.ollama_base_url,
            settings.ollama_eval_model,
            settings.ollama_eval_timeout_seconds,
        )
    except ReportEvaluationError as exc:
        logger.warning("Batch report eval failed: %s", exc)
        result = {
            "batch_id": batch_id,
            "status": "failed",
            "error": str(exc),
            "items": [],
            "summary": "Batch evaluation failed.",
        }

    result_record = {
        "batch_id": batch_id,
        "created_at": datetime.now(UTC).isoformat(),
        "batch_file": str(batch_file),
        "model": settings.ollama_eval_model,
        "result": result,
    }
    with EVAL_RESULTS_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(result_record, ensure_ascii=False, default=str) + "\n")
    _mark_batch_complete(batch_id, result)
    return result_record


async def _evaluate_with_ollama(
    payload: dict[str, Any],
    base_url: str,
    model: str,
    timeout_seconds: int,
) -> ReportEvaluation:
    prompt = (
        "You are an evaluation judge for a MySQL reporting assistant.\n"
        "Use only the supplied question, SQL, schema summary, execution facts, columns, and sample rows.\n"
        "Backend validation proves technical schema/execution facts; your job is semantic fit.\n"
        "Do not invent schema facts.\n"
        "Score from 0 to 100: 90-100 excellent, 75-89 acceptable, 60-74 questionable, below 60 failed.\n"
        "Set passed=true only when score is 75 or higher and no major issue is present.\n"
        "Return JSON only with keys: passed, score, verdict, validation_type, issues, suggestions.\n\n"
        f"Evaluation evidence:\n{json.dumps(payload, default=str)}"
    )
    body = {
        "model": model,
        "stream": False,
        "format": "json",
        "prompt": prompt,
        "options": {
            "temperature": 0,
            "num_predict": 350,
        },
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(f"{base_url.rstrip('/')}/api/generate", json=body)
            response.raise_for_status()
        data = response.json()
        content = data.get("response") or "{}"
        return _parse_evaluation(content)
    except httpx.HTTPStatusError as exc:
        raise ReportEvaluationError(f"Ollama eval returned HTTP {exc.response.status_code}.") from exc
    except httpx.TimeoutException as exc:
        raise ReportEvaluationError(
            f"Ollama eval timed out after {timeout_seconds} seconds. "
            "The qwen2.5:3b model may still be loading or the eval prompt may be too large."
        ) from exc
    except httpx.RequestError as exc:
        raise ReportEvaluationError(
            f"Ollama eval request failed at {exc.request.url}: {exc.__class__.__name__}: {exc!r}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ReportEvaluationError(f"Ollama eval returned invalid JSON: {exc}") from exc
    except Exception as exc:
        raise ReportEvaluationError(f"Ollama eval failed: {exc.__class__.__name__}: {exc!r}") from exc


async def _evaluate_batch_with_ollama(
    batch_payload: dict[str, Any],
    base_url: str,
    model: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    prompt = (
        "You are a batch evaluation judge for a MySQL reporting assistant.\n"
        "Each record contains one user question, generated SQL, backend validation facts, columns, and sample rows.\n"
        "Backend validation already checks SQL safety, schema references, and execution where available.\n"
        "Your job is not only SQL syntax checking. Judge semantic fit: whether the SQL/report likely answers the user's question.\n"
        "For every item, evaluate all rubric points, even when SQL executed successfully.\n"
        "Rubric points: intent_match, date_filter, grouping, metrics, columns_rows, explanation_match, assumptions_quality, backend_execution.\n"
        "For each rubric point return status pass/warn/fail, evidence, and note.\n"
        "If deterministic_hints says the question needs dates and SQL has no date condition, date_filter must be warn or fail.\n"
        "If deterministic_hints says the question needs grouping and SQL has no GROUP BY or grouped output, grouping must be warn or fail.\n"
        "If deterministic_hints says the question needs totals/count/top metrics and SQL lacks aggregate/order/limit signals, metrics must be warn or fail.\n"
        "If deterministic_hints.requested_limit is set and SQL limit or row_count is greater than requested_limit, metrics and columns_rows must fail.\n"
        "If the question asks for top N, the report must return at most N rows and SQL should contain LIMIT N or an equivalent top-N restriction.\n"
        "If columns or sample rows do not match the question wording, columns_rows must be warn or fail.\n"
        "If explanation claims filters/grouping/metrics not present in SQL, explanation_match must be warn or fail.\n"
        "If assumptions claim the backend will add a specific limit but SQL/output contradict it, assumptions_quality must fail.\n"
        "If backend_validation.sql_executed is false, backend_execution must be warn or fail unless dry_run is true.\n"
        "Use schema_evidence only as context; do not invent tables or columns beyond it.\n"
        "Return JSON only with keys: batch_id, status, summary, items.\n"
        "Each item must contain: id, passed, score, verdict, checks, issues, suggestions.\n"
        "checks must be an object with all rubric point names as keys.\n"
        "Each checks entry must be an object like {\"status\":\"pass|warn|fail\",\"evidence\":\"specific evidence\",\"note\":\"short reason\"}; do not return plain strings for checks.\n"
        "Always include all eight check keys: intent_match, date_filter, grouping, metrics, columns_rows, explanation_match, assumptions_quality, backend_execution.\n"
        "Score weighting: intent_match 25, backend_execution 15, date_filter 12, grouping 12, metrics 12, columns_rows 10, explanation_match 8, assumptions_quality 6.\n"
        "Score from 0 to 100. passed=true only when score is 75 or higher and no rubric point has status fail.\n"
        "The verdict must mention at least two non-SQL aspects such as date filter, grouping, output columns, sample rows, explanation, or assumptions.\n\n"
        f"Batch evidence:\n{json.dumps(batch_payload, separators=(',', ':'), default=str)}"
    )
    body = {
        "model": model,
        "stream": False,
        "format": "json",
        "prompt": prompt,
        "options": {
            "temperature": 0,
            "num_predict": 600,
        },
    }
    try:
        response = await _post_ollama_generate(base_url, body, timeout_seconds)
        data = response.json()
        raw_content = data.get("response") or "{}"
        return _parse_batch_evaluation(raw_content, batch_payload["batch_id"])
    except httpx.HTTPStatusError as exc:
        raise ReportEvaluationError(f"Ollama batch eval returned HTTP {exc.response.status_code}.") from exc
    except httpx.TimeoutException as exc:
        raise ReportEvaluationError(f"Ollama batch eval timed out after {timeout_seconds} seconds.") from exc
    except httpx.RequestError as exc:
        raise ReportEvaluationError(
            f"Ollama batch eval request failed at {exc.request.url}: {exc.__class__.__name__}: {exc!r}"
        ) from exc
    except json.JSONDecodeError as exc:
        raw = locals().get("raw_content", "")
        raise ReportEvaluationError(
            f"Ollama batch eval returned invalid JSON: {exc}; raw_response={_short_text(raw, 1200)}"
        ) from exc
    except Exception as exc:
        raise ReportEvaluationError(f"Ollama batch eval failed: {exc.__class__.__name__}: {exc!r}") from exc


def _parse_evaluation(content: str) -> ReportEvaluation:
    parsed = json.loads(_extract_json(content))
    score = int(parsed.get("score") or 0)
    score = max(0, min(score, 100))
    issues = _string_list(parsed.get("issues"))
    return ReportEvaluation(
        passed=bool(parsed.get("passed")) and score >= 75 and not issues,
        score=score,
        verdict=parsed.get("verdict") or "No evaluation verdict returned.",
        validation_type=parsed.get("validation_type") or "intent_and_result",
        issues=issues,
        suggestions=_string_list(parsed.get("suggestions")),
    )


async def _post_ollama_generate(base_url: str, body: dict[str, Any], timeout_seconds: int) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in (1, 2):
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(f"{base_url.rstrip('/')}/api/generate", json=body)
                response.raise_for_status()
                return response
        except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError) as exc:
            last_error = exc
            if attempt == 1:
                await asyncio.sleep(2)
                continue
            raise
    raise last_error or ReportEvaluationError("Ollama request failed.")


def _parse_batch_evaluation(content: str, batch_id: str) -> dict[str, Any]:
    json_content = _extract_json(content)
    try:
        parsed = json.loads(json_content)
    except json.JSONDecodeError:
        parsed = _recover_batch_evaluation(json_content, batch_id)
        if parsed is None:
            raise
    return _normalize_batch_result(parsed, batch_id)


def _recover_batch_evaluation(content: str, batch_id: str) -> dict[str, Any] | None:
    item_blocks = re.findall(r"\{[^{}]*\"id\"\s*:\s*\"[^\"]+\".*?\"suggestions\"\s*:\s*\[[^\]]*\][^{}]*\}", content, re.DOTALL)
    items = []
    for block in item_blocks:
        try:
            items.append(_normalize_eval_item(json.loads(block)))
        except json.JSONDecodeError:
            item = _recover_eval_item(block)
            if item:
                items.append(item)
    if not items:
        return None
    return {
        "batch_id": batch_id,
        "status": "recovered",
        "summary": "Recovered item-level evaluation from malformed Ollama JSON.",
        "items": items,
    }


def _recover_eval_item(block: str) -> dict[str, Any] | None:
    id_match = re.search(r"\"id\"\s*:\s*\"([^\"]+)\"", block)
    if not id_match:
        return None
    score_match = re.search(r"\"score\"\s*:\s*([0-9]+(?:\.[0-9]+)?)", block)
    passed_match = re.search(r"\"passed\"\s*:\s*(true|false)", block, re.IGNORECASE)
    verdict_match = re.search(r"\"verdict\"\s*:\s*\"([^\"]*)\"", block, re.DOTALL)
    return _normalize_eval_item(
        {
            "id": id_match.group(1),
            "passed": (passed_match.group(1).lower() == "true") if passed_match else False,
            "score": float(score_match.group(1)) if score_match else 0,
            "verdict": verdict_match.group(1) if verdict_match else "Recovered from malformed evaluator JSON.",
            "checks": {},
            "issues": _recover_string_array(block, "issues"),
            "suggestions": _recover_string_array(block, "suggestions"),
        }
    )


def _normalize_batch_result(parsed: dict[str, Any], batch_id: str) -> dict[str, Any]:
    items = [_normalize_eval_item(item) for item in parsed.get("items", []) if isinstance(item, dict)]
    return {
        "batch_id": parsed.get("batch_id") or batch_id,
        "status": parsed.get("status") or "success",
        "summary": parsed.get("summary") or "Batch evaluation completed.",
        "items": items,
    }


def _normalize_eval_item(item: dict[str, Any]) -> dict[str, Any]:
    score = _bounded_score(item.get("score"))
    checks = _normalize_checks(item.get("checks"))
    has_failed_check = any(check.get("status") == "fail" for check in checks.values())
    issues = _string_list(item.get("issues"))
    return {
        "id": item.get("id"),
        "passed": bool(item.get("passed")) and score >= 75 and not has_failed_check,
        "score": score,
        "verdict": item.get("verdict") or "No verdict returned.",
        "checks": checks,
        "issues": issues,
        "suggestions": _string_list(item.get("suggestions")),
    }


def _normalize_checks(value: Any) -> dict[str, dict[str, str]]:
    required = [
        "intent_match",
        "date_filter",
        "grouping",
        "metrics",
        "columns_rows",
        "explanation_match",
        "assumptions_quality",
        "backend_execution",
    ]
    checks = value if isinstance(value, dict) else {}
    normalized = {}
    for key in required:
        item = checks.get(key)
        if isinstance(item, dict):
            status = str(item.get("status") or "warn").lower()
            normalized[key] = {
                "status": status if status in {"pass", "warn", "fail"} else "warn",
                "evidence": str(item.get("evidence") or ""),
                "note": str(item.get("note") or ""),
            }
        elif isinstance(item, str):
            normalized[key] = {
                "status": item if item in {"pass", "warn", "fail"} else "warn",
                "evidence": "",
                "note": "Evaluator returned a compact string check.",
            }
        else:
            normalized[key] = {
                "status": "warn",
                "evidence": "",
                "note": "Evaluator did not return this check.",
            }
    return normalized


def _bounded_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0
    return max(0, min(score, 100))


def _recover_string_array(content: str, key: str) -> list[str]:
    match = re.search(rf"\"{re.escape(key)}\"\s*:\s*\[(.*?)\]", content, re.DOTALL)
    if not match:
        return []
    return re.findall(r"\"([^\"]+)\"", match.group(1))


def _safe_schema_summary() -> dict[str, Any]:
    try:
        schema = schema_service.get_schema(force_refresh=False)
    except Exception as exc:
        logger.warning("Could not load schema for eval: %s", exc)
        return {
            "source": "unavailable",
            "fetched_at": None,
            "table_count": 0,
            "column_count": 0,
            "tables": [],
        }

    tables = []
    column_count = 0
    for table in schema.get("tables", []):
        columns = [
            {
                "name": column.get("name"),
                "type": column.get("type"),
                "description": column.get("description", ""),
            }
            for column in table.get("columns", [])
        ]
        column_count += len(columns)
        tables.append(
            {
                "name": table.get("name"),
                "description": table.get("description", ""),
                "columns": columns,
            }
        )

    return {
        "source": ",".join(schema.get("source_files", [])) or "schema_catalog",
        "fetched_at": schema.get("fetched_at"),
        "table_count": len(tables),
        "column_count": column_count,
        "relationships": schema.get("relationships", [])[:50],
        "tables": tables,
    }


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _build_eval_record(payload: dict[str, Any]) -> dict[str, Any]:
    report = payload["report"]
    backend_validation = payload["backend_validation"]
    schema_summary = payload["schema_summary"]
    return {
        "id": str(uuid4()),
        "created_at": datetime.now(UTC).isoformat(),
        "eval_status": "pending",
        "eval_batch_id": None,
        "eval_started_at": None,
        "eval_finished_at": None,
        "eval_result": None,
        "question": payload["question"],
        "report": {
            "title": report["title"],
            "sql": report["sql"],
            "explanation": report["explanation"],
            "assumptions": report["assumptions"],
            "columns": report["columns"],
            "sample_rows": report["sample_rows"][:3],
            "row_count": report["row_count"],
            "dry_run": report["dry_run"],
            "warnings": report["warnings"],
        },
        "backend_validation": {
            "schema_available": backend_validation["schema_available"],
            "schema_source": backend_validation["schema_source"],
            "schema_fetched_at": backend_validation["schema_fetched_at"],
            "table_count": backend_validation["table_count"],
            "column_count": backend_validation["column_count"],
            "sql_executed": backend_validation["sql_executed"],
            "retry_attempts": backend_validation["retry_attempts"],
        },
        "evaluation_checklist": [
            "Does the SQL answer the natural-language question, not just execute?",
            "Are requested date/week/month/year filters represented in SQL?",
            "Are requested grouping dimensions selected and grouped?",
            "Are requested totals/counts/top metrics calculated correctly?",
            "Do output columns and sample rows match the requested report?",
            "Does the explanation match the actual SQL?",
        ],
        "deterministic_hints": _deterministic_hints(payload["question"], report),
        "schema_evidence": _schema_evidence(report["sql"], schema_summary),
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            records.append(_normalize_eval_record(json.loads(line)))
    return records


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    if not records:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _normalize_eval_record(record: dict[str, Any]) -> dict[str, Any]:
    if "eval_status" in record:
        return record
    return {
        **record,
        "eval_status": "pending",
        "eval_batch_id": None,
        "eval_started_at": None,
        "eval_finished_at": None,
        "eval_result": None,
    }


def _mark_batch_complete(batch_id: str, result: dict[str, Any]) -> None:
    records = _read_jsonl(EVAL_QUEUE_PATH)
    item_results = {
        item.get("id"): item
        for item in result.get("items", [])
        if isinstance(item, dict) and item.get("id")
    }
    batch_failed = result.get("status") == "failed"
    updated = []
    for record in records:
        if record.get("eval_batch_id") != batch_id:
            updated.append(record)
            continue
        item_result = item_results.get(record.get("id"))
        missing_item = item_result is None
        updated.append(
            {
                **record,
                "eval_status": "eval_failed" if batch_failed or missing_item else "evaluated",
                "eval_finished_at": datetime.now(UTC).isoformat(),
                "eval_result": item_result or {
                    "passed": False,
                    "score": 0,
                    "verdict": result.get("summary") or "No item-level result returned.",
                    "issues": [result.get("error") or "No item-level evaluation was returned."],
                    "suggestions": [],
                },
            }
        )
    _write_jsonl(EVAL_QUEUE_PATH, updated)


def _compact_eval_record_for_model(record: dict[str, Any]) -> dict[str, Any]:
    report = record.get("report", {})
    backend_validation = record.get("backend_validation", {})
    return {
        "id": record.get("id"),
        "question": record.get("question"),
        "report": {
            "title": report.get("title"),
            "sql": report.get("sql"),
            "explanation": report.get("explanation"),
            "assumptions": (report.get("assumptions") or [])[:5],
            "columns": report.get("columns") or [],
            "sample_rows": (report.get("sample_rows") or [])[:2],
            "row_count": report.get("row_count"),
            "dry_run": report.get("dry_run"),
            "warnings": report.get("warnings") or [],
        },
        "backend_validation": {
            "schema_available": backend_validation.get("schema_available"),
            "schema_source": backend_validation.get("schema_source"),
            "sql_executed": backend_validation.get("sql_executed"),
            "retry_attempts": [
                {
                    "attempt": attempt.get("attempt"),
                    "status": attempt.get("status"),
                    "message": attempt.get("message"),
                    "schema_issue": attempt.get("schema_issue"),
                }
                for attempt in backend_validation.get("retry_attempts", [])
            ],
        },
        "evaluation_checklist": record.get("evaluation_checklist", []),
        "deterministic_hints": record.get("deterministic_hints")
        or _deterministic_hints(str(record.get("question", "")), report),
        "schema_evidence": _compact_schema_evidence(record),
    }


def _compact_schema_evidence(record: dict[str, Any]) -> dict[str, Any]:
    schema_evidence = record.get("schema_evidence") or {}
    sql_lower = str(record.get("report", {}).get("sql", "")).lower()
    output_columns = {
        str(column).lower()
        for column in record.get("report", {}).get("columns", [])
    }
    matched_tables = []
    for table in schema_evidence.get("matched_tables", [])[:6]:
        columns = []
        for column in table.get("columns", []):
            name = str(column.get("name", ""))
            if name.lower() in sql_lower or name.lower() in output_columns:
                columns.append(
                    {
                        "name": name,
                        "type": column.get("type"),
                        "description": column.get("description", ""),
                    }
                )
        matched_tables.append(
            {
                "name": table.get("name"),
                "description": table.get("description", ""),
                "columns": columns[:20],
            }
        )
    return {
        "schema_source": schema_evidence.get("schema_source"),
        "schema_fetched_at": schema_evidence.get("schema_fetched_at"),
        "matched_tables": matched_tables,
        "relationships": (schema_evidence.get("relationships") or [])[:10],
    }


def _deterministic_hints(question: str, report: dict[str, Any]) -> dict[str, Any]:
    question_lower = question.lower()
    sql = str(report.get("sql") or "")
    sql_lower = sql.lower()
    columns = [str(column).lower() for column in report.get("columns", [])]
    explanation_lower = str(report.get("explanation") or "").lower()
    sample_rows = report.get("sample_rows") or []
    requested_limit = _requested_limit(question_lower)
    sql_limit = _sql_limit(sql_lower)
    row_count = report.get("row_count")
    return {
        "requested_limit": requested_limit,
        "question_needs": {
            "date_filter": _contains_any(
                question_lower,
                ["week", "month", "year", "today", "yesterday", "april", "2026", "date", "daily", "weekly", "monthly"],
            ),
            "grouping": _contains_any(question_lower, ["group", "grouped", "by ", "wise", "per ", "summary by"]),
            "totals_or_counts": _contains_any(
                question_lower,
                ["total", "count", "sum", "average", "avg", "percentage", "percent", "hours", "tickets", "tasks"],
            ),
            "top_or_ordering": _contains_any(question_lower, ["top", "highest", "lowest", "most", "least", "greater than", "below"]),
            "status_filter": _contains_any(question_lower, ["active", "completed", "pending", "open", "closed", "status"]),
        },
        "sql_signals": {
            "has_date_condition": _contains_any(sql_lower, ["date(", "created_at", "updated_at", "between", "month(", "year(", "week(", "start_date", "end_date"]),
            "has_group_by": "group by" in sql_lower,
            "has_aggregate": _contains_any(sql_lower, ["count(", "sum(", "avg(", "min(", "max(", "round("]),
            "has_order_or_limit": "order by" in sql_lower or "limit" in sql_lower,
            "limit_value": sql_limit,
            "limit_matches_requested": requested_limit is None or sql_limit == requested_limit,
            "limit_exceeds_requested": requested_limit is not None and sql_limit is not None and sql_limit > requested_limit,
            "has_status_condition": "status" in sql_lower,
            "has_where": " where " in f" {sql_lower} ",
        },
        "output_signals": {
            "columns": columns,
            "row_count": row_count,
            "row_count_matches_requested_limit": requested_limit is None or (
                isinstance(row_count, int) and row_count <= requested_limit
            ),
            "row_count_exceeds_requested_limit": requested_limit is not None
            and isinstance(row_count, int)
            and row_count > requested_limit,
            "sample_row_count": len(sample_rows),
            "has_numeric_output": any(
                isinstance(value, (int, float)) or _looks_numeric(value)
                for row in sample_rows
                if isinstance(row, dict)
                for value in row.values()
            ),
            "explanation_mentions_date": _contains_any(explanation_lower, ["week", "month", "year", "date"]),
            "explanation_mentions_grouping": _contains_any(explanation_lower, ["group", "grouped", "by project", "by team", "by type"]),
        },
    }


def _contains_any(value: str, needles: list[str]) -> bool:
    return any(needle in value for needle in needles)


def _requested_limit(question: str) -> int | None:
    patterns = [
        r"\btop\s+(\d{1,3})\b",
        r"\bfirst\s+(\d{1,3})\b",
        r"\blast\s+(\d{1,3})\b",
        r"\blimit\s+(\d{1,3})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, question)
        if match:
            return int(match.group(1))
    return None


def _sql_limit(sql: str) -> int | None:
    matches = re.findall(r"\blimit\s+(\d{1,5})\b", sql)
    if not matches:
        return None
    return int(matches[-1])


def _looks_numeric(value: Any) -> bool:
    if value is None:
        return False
    try:
        float(str(value))
        return True
    except ValueError:
        return False


def _schema_evidence(sql: str, schema_summary: dict[str, Any]) -> dict[str, Any]:
    sql_lower = sql.lower()
    matched_tables = []
    matched_names: set[str] = set()
    for table in schema_summary.get("tables", []):
        name = table.get("name")
        if not name or name.lower() not in sql_lower:
            continue
        matched_names.add(name)
        matched_tables.append(
            {
                "name": name,
                "description": table.get("description", ""),
                "columns": [
                    {
                        "name": column.get("name"),
                        "type": column.get("type"),
                        "description": column.get("description", ""),
                    }
                    for column in table.get("columns", [])
                ],
            }
        )
        if len(matched_tables) >= 12:
            break

    relationships = []
    for relationship in schema_summary.get("relationships", []):
        from_ref = str(relationship.get("from", ""))
        to_ref = str(relationship.get("to", ""))
        if any(from_ref.startswith(f"{name}.") or to_ref.startswith(f"{name}.") for name in matched_names):
            relationships.append(relationship)
        if len(relationships) >= 20:
            break

    return {
        "schema_source": schema_summary.get("source"),
        "schema_fetched_at": schema_summary.get("fetched_at"),
        "matched_tables": matched_tables,
        "relationships": relationships,
    }


def _extract_json(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return stripped[start : end + 1]
    return "{}"


def _short_text(value: Any, limit: int) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."
