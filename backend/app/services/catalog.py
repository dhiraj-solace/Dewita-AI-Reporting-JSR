import json
from functools import lru_cache
from pathlib import Path
from typing import Any
import httpx

from app.core.config import get_settings

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def load_schema_catalog() -> dict[str, Any]:
    try:
        from .schema_service import schema_service
        return schema_service.get_schema()
    except Exception:
        return json.loads((DATA_DIR / "schema_catalog.json").read_text(encoding="utf-8"))


@lru_cache
def load_report_catalog() -> dict[str, Any]:
    return json.loads((DATA_DIR / "report_catalog.json").read_text(encoding="utf-8"))


@lru_cache
def load_report_categories() -> dict[str, Any]:
    path = DATA_DIR / "report_categories.json"
    if not path.exists():
        return {"categories": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    categories = [
        category
        for category in data.get("categories", [])
        if category.get("enabled", True)
    ]
    if not any(category.get("id") == "auto" for category in categories):
        categories.insert(
            0,
            {
                "id": "auto",
                "label": "Auto Detect",
                "enabled": True,
                "match_keywords": [],
                "allowed_tables": [],
                "preferred_tables": [],
                "metrics": [],
                "filters": [],
                "templates": [],
                "strict_mode": False,
            },
        )
    if not any(category.get("id") == "custom" for category in categories):
        categories.insert(
            1,
            {
                "id": "custom",
                "label": "Custom Report",
                "enabled": True,
                "match_keywords": [],
                "allowed_tables": [],
                "preferred_tables": [],
                "metrics": [],
                "filters": [],
                "templates": [],
                "strict_mode": False,
            },
        )
    return {"categories": categories}


def resolve_report_category(category_id: str | None, question: str = "") -> dict[str, Any] | None:
    categories = load_report_categories().get("categories", [])
    normalized_id = (category_id or "").strip().lower()
    if normalized_id and normalized_id != "auto":
        return next((category for category in categories if category.get("id") == normalized_id), None)

    normalized_question = question.lower()
    scored: list[tuple[int, dict[str, Any]]] = []
    for category in categories:
        if category.get("id") == "custom":
            continue
        score = sum(1 for keyword in category.get("match_keywords", []) if str(keyword).lower() in normalized_question)
        if score:
            scored.append((score, category))
    if scored:
        return sorted(scored, key=lambda item: item[0], reverse=True)[0][1]
    return next((category for category in categories if category.get("id") == "custom"), None)


async def resolve_report_category_with_ai(category_id: str | None, question: str = "") -> dict[str, Any] | None:
    categories = load_report_categories().get("categories", [])
    normalized_id = (category_id or "").strip().lower()
    if normalized_id and normalized_id != "auto":
        return next((category for category in categories if category.get("id") == normalized_id), None)

    detected_id = await _detect_category_with_openrouter(question, categories)
    if detected_id:
        detected = next((category for category in categories if category.get("id") == detected_id), None)
        if detected:
            return detected
    return resolve_report_category(category_id, question)


async def _detect_category_with_openrouter(question: str, categories: list[dict[str, Any]]) -> str | None:
    settings = get_settings()
    if not settings.openrouter_api_key:
        return None
    choices = [
        {
            "id": category.get("id"),
            "label": category.get("label"),
            "match_keywords": category.get("match_keywords", [])[:12],
            "preferred_tables": category.get("preferred_tables", [])[:10],
            "metrics": category.get("metrics", [])[:10],
        }
        for category in categories
        if category.get("id") not in {"auto", "custom"} and category.get("enabled", True)
    ]
    if not choices:
        return None
    prompt = (
        "Classify the user's report question into exactly one report category id. "
        "Use semantic intent, not only keywords. Return compact JSON only with "
        "{\"category_id\":\"...\", \"reason\":\"...\"}. If no category fits, use custom."
    )
    body = {
        "model": settings.openrouter_intent_model or settings.openrouter_model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": json.dumps(
                    {"question": question, "categories": choices + [{"id": "custom", "label": "Custom Report"}]},
                    ensure_ascii=False,
                ),
            },
        ],
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {settings.openrouter_api_key}"}
    if settings.openrouter_site_url:
        headers["HTTP-Referer"] = settings.openrouter_site_url
    if settings.openrouter_app_name:
        headers["X-Title"] = settings.openrouter_app_name
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=body)
            response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"] or "{}"
        parsed = json.loads(content)
        category_id = str(parsed.get("category_id") or "").strip().lower()
        allowed_ids = {str(category.get("id") or "").lower() for category in choices}
        return category_id if category_id in allowed_ids else None
    except Exception:
        return None


def category_context(category: dict[str, Any] | None) -> dict[str, Any] | None:
    if not category or category.get("id") == "custom":
        return None
    return {
        "id": category.get("id"),
        "label": category.get("label"),
        "preferred_tables": category.get("preferred_tables", []),
        "allowed_tables": category.get("allowed_tables", []),
        "metrics": category.get("metrics", []),
        "filters": category.get("filters", []),
        "templates": category.get("templates", []),
        "strict_mode": bool(category.get("strict_mode", False)),
    }


def catalog_context(category: dict[str, Any] | None = None) -> str:
    schema = load_schema_catalog()
    reports = load_report_catalog()
    category_info = category_context(category)
    allowed_tables = set(category_info.get("allowed_tables") or []) if category_info and category_info.get("strict_mode") else set()
    tables = []
    for table in schema["tables"]:
        if allowed_tables and table["name"] not in allowed_tables:
            continue
        columns = ", ".join(column["name"] for column in table["columns"])
        aliases = f" aliases={table.get('aliases', [])}" if table.get("aliases") else ""
        tables.append(f"- {table['name']}{aliases}: {columns}")
    report_lines = []
    for report in reports["reports"]:
        report_lines.append(
            f"- {report['name']}: tables={', '.join(report['tables'])}; metrics={'; '.join(report['metrics'])}"
        )
    category_lines = []
    if category_info:
        category_lines = [
            f"Selected report category: {category_info['label']} ({category_info['id']})",
            f"Preferred tables: {', '.join(category_info['preferred_tables']) or 'none configured'}",
            f"Allowed tables: {', '.join(category_info['allowed_tables']) or 'not restricted'}",
            f"Metrics: {', '.join(category_info['metrics']) or 'not configured'}",
            f"Filters: {', '.join(category_info['filters']) or 'not configured'}",
            f"Strict mode: {category_info['strict_mode']}",
        ]
    parts = []
    if category_lines:
        parts.append("REPORT CATEGORY\n" + "\n".join(category_lines))
    parts.append("SCHEMA\n" + "\n".join(tables))
    parts.append("REPORTS\n" + "\n".join(report_lines))
    return "\n\n".join(parts)
