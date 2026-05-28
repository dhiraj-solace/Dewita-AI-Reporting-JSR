import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

ALLOWED_INTENTS = {
    "read_report",
    "list_records",
    "count_records",
    "summarize_records",
    "compare_records",
    "export_report",
}

BLOCKED_INTENTS = {
    "create_record",
    "update_record",
    "delete_record",
    "schema_change",
    "admin_action",
    "credential_request",
    "execute_code",
    "non_reporting",
}

INTENT_SYSTEM_PROMPT = """You are a strict intent safety classifier for a business reporting app.
Classify the user's natural-language request by intent, not by individual keywords.

Allow only read-only reporting intent:
- viewing, listing, counting, summarizing, comparing, ranking, filtering, or exporting existing business data.
- phrases like "created users", "deleted users", or "updated tasks" can be safe when they describe records/status/history to view.

Block mutation/admin intent:
- creating, inserting, updating, changing, approving, deleting, restoring, archiving, dropping, altering, granting, executing code, or requesting credentials/secrets.

Return only compact JSON with this exact shape:
{
  "intent": "read_report|list_records|count_records|summarize_records|compare_records|export_report|create_record|update_record|delete_record|schema_change|admin_action|credential_request|execute_code|non_reporting",
  "is_safe": true,
  "reason": "short reason",
  "risk": "low|medium|high"
}
"""


@dataclass
class QuerySafetyResult:
    is_safe: bool
    reason: str = ""
    blocked_operation: str | None = None
    intent: str | None = None
    risk: str | None = None


async def validate_user_query_safety(query: str) -> QuerySafetyResult:
    """Classify user intent with OpenRouter instead of keyword blocking."""
    normalized = " ".join(query.strip().split())
    if not normalized:
        return QuerySafetyResult(False, "Question is empty.", intent="non_reporting", risk="low")

    settings = get_settings()
    if not settings.openrouter_api_key:
        return QuerySafetyResult(
            False,
            "OpenRouter intent safety classifier is not configured.",
            blocked_operation="INTENT_CLASSIFIER",
            intent="non_reporting",
            risk="high",
        )

    try:
        classification = await _classify_intent_with_openrouter(normalized)
    except Exception as exc:
        logger.warning("Intent safety classification failed: %s", exc)
        return QuerySafetyResult(
            False,
            "Unable to verify the request intent safely. Please try again after the intent classifier is available.",
            blocked_operation="INTENT_CLASSIFIER",
            intent="non_reporting",
            risk="high",
        )

    intent = str(classification.get("intent") or "non_reporting").strip().lower()
    reason = str(classification.get("reason") or "Request intent was classified.").strip()
    risk = str(classification.get("risk") or "medium").strip().lower()
    is_safe = bool(classification.get("is_safe")) and intent in ALLOWED_INTENTS
    if intent in BLOCKED_INTENTS:
        is_safe = False

    if is_safe:
        return QuerySafetyResult(True, reason=reason, intent=intent, risk=risk)
    return QuerySafetyResult(
        False,
        reason or "Only read-only reporting intent is allowed.",
        blocked_operation=intent.upper(),
        intent=intent,
        risk=risk,
    )


async def _classify_intent_with_openrouter(query: str) -> dict[str, Any]:
    settings = get_settings()
    model = settings.openrouter_intent_model or settings.openrouter_model
    headers = {"Authorization": f"Bearer {settings.openrouter_api_key}"}
    if settings.openrouter_site_url:
        headers["HTTP-Referer"] = settings.openrouter_site_url
    if settings.openrouter_app_name:
        headers["X-Title"] = settings.openrouter_app_name

    body = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": INTENT_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({"question": query}, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
    }
    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=body,
        )
        response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"] or "{}"
    return _parse_json_object(content)


def _parse_json_object(content: str) -> dict[str, Any]:
    try:
        value = json.loads(content)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(content[start : end + 1])
                return value if isinstance(value, dict) else {}
            except json.JSONDecodeError:
                return {}
    return {}
