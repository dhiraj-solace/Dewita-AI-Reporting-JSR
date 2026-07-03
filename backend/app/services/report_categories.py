import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.llm_sql_cache import normalize_query

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DEFAULT_CATEGORY_ID = "custom"
AUTO_CATEGORY_ID = "auto"


@lru_cache
def load_report_categories() -> dict[str, Any]:
    data = json.loads((DATA_DIR / "report_categories.json").read_text(encoding="utf-8"))
    data["categories"] = [
        category
        for category in data.get("categories", [])
        if category.get("enabled", True)
    ]
    return data


def list_report_categories() -> dict[str, Any]:
    return {
        "categories": [
            {
                "id": category["id"],
                "label": category["label"],
                "strict_mode": bool(category.get("strict_mode", False)),
            }
            for category in load_report_categories().get("categories", [])
        ]
    }


def resolve_report_category(question: str, selected_category: str | None) -> dict[str, Any]:
    categories = load_report_categories().get("categories", [])
    category_by_id = {str(category.get("id")): category for category in categories}
    requested = (selected_category or AUTO_CATEGORY_ID).strip().lower()

    if requested and requested not in {AUTO_CATEGORY_ID, DEFAULT_CATEGORY_ID}:
        return category_by_id.get(requested) or category_by_id.get(DEFAULT_CATEGORY_ID) or _fallback_category()

    if requested == DEFAULT_CATEGORY_ID:
        return category_by_id.get(DEFAULT_CATEGORY_ID) or _fallback_category()

    detected = _detect_category(question, categories)
    return detected or category_by_id.get(DEFAULT_CATEGORY_ID) or _fallback_category()


def build_category_prompt_context(category: dict[str, Any]) -> dict[str, Any]:
    category_id = str(category.get("id") or DEFAULT_CATEGORY_ID)
    if category_id in {AUTO_CATEGORY_ID, DEFAULT_CATEGORY_ID}:
        return {
            "report_category": category_id,
            "strict_mode": False,
            "requirements": [
                "No fixed report category was selected. Use the schema catalog normally.",
            ],
        }

    context = {
        "report_category": category_id,
        "report_category_label": category.get("label"),
        "strict_mode": bool(category.get("strict_mode", False)),
        "preferred_tables": category.get("preferred_tables") or [],
        "allowed_tables": category.get("allowed_tables") or [],
        "metrics": category.get("metrics") or [],
        "filters": category.get("filters") or [],
        "dimensions": category.get("dimensions") or [],
        "templates": category.get("templates") or [],
        "requirements": [
            "Use the selected report category as guidance for tables, metrics, filters, and output shape.",
            "Prefer preferred_tables and category metrics when they match the user's question.",
            "If strict_mode is false, you may use other documented schema tables when required by the question.",
            "If strict_mode is true, use only allowed_tables unless the category config leaves allowed_tables empty.",
        ],
    }
    return context


def category_template_titles(category: dict[str, Any] | None) -> set[str]:
    if not category:
        return set()
    return {str(title).lower() for title in category.get("templates") or []}


def _detect_category(question: str, categories: list[dict[str, Any]]) -> dict[str, Any] | None:
    normalized = normalize_query(question)
    scored: list[tuple[int, dict[str, Any]]] = []
    for category in categories:
        category_id = str(category.get("id") or "")
        if category_id in {AUTO_CATEGORY_ID, DEFAULT_CATEGORY_ID}:
            continue
        score = sum(1 for keyword in category.get("match_keywords") or [] if normalize_query(str(keyword)) in normalized)
        if score:
            scored.append((score, category))
    if not scored:
        return None
    return sorted(scored, key=lambda item: item[0], reverse=True)[0][1]


def _fallback_category() -> dict[str, Any]:
    return {
        "id": DEFAULT_CATEGORY_ID,
        "label": "Custom Report",
        "enabled": True,
        "strict_mode": False,
        "match_keywords": [],
        "preferred_tables": [],
        "allowed_tables": [],
        "metrics": [],
        "filters": [],
        "dimensions": [],
        "templates": [],
    }
