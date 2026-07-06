import re
from datetime import date, datetime
from typing import Any


WEEK_FIVE_PALETTE = {
    "header": "#00CED1",
    "project_cad": "#00FFFF",
    "project_active": "#008000",
    "project_not_started": "#FFFF00",
    "production_week": "#FF00FF",
    "approval_week": "#CED4DA",
    "task_week": "#FFFF00",
    "empty_week": "#FFFFFF",
    "combined_total": "#B5B576",
    "section_total": "#B2C8ED",
    "grand_total": "#28A745",
    "section_header": "#F5F5DC",
    "comments_present": "#008000",
    "comments_missing": "#DC3545",
    "comments_error": "#FD7E14",
}

WEEK_FIVE_LEGEND = [
    {"key": "project_active", "label": "Project in process", "background": WEEK_FIVE_PALETTE["project_active"], "foreground": "#FFFFFF"},
    {"key": "project_not_started", "label": "Project not started / tasks planned", "background": WEEK_FIVE_PALETTE["project_not_started"], "foreground": "#111827"},
    {"key": "approval_week", "label": "Out for approval week", "background": WEEK_FIVE_PALETTE["approval_week"], "foreground": "#111827"},
    {"key": "production_week", "label": "Production week", "background": WEEK_FIVE_PALETTE["production_week"], "foreground": "#111827"},
]


def build_report_presentation(
    title: str,
    question: str,
    columns: list[str],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if not _is_week_five(title, question):
        return {}

    presentation: dict[str, Any] = {
        "variant": "week_five",
        "legend": WEEK_FIVE_LEGEND,
        "header_style": _style("header", foreground="#111827"),
        "row_styles": {},
        "cell_styles": {},
    }
    for row_index, row in enumerate(rows):
        row_style = _row_style(row)
        if row_style:
            presentation["row_styles"][str(row_index)] = row_style
            continue
        cell_styles = _cell_styles(columns, row)
        if cell_styles:
            presentation["cell_styles"][str(row_index)] = cell_styles
    return presentation


def _is_week_five(title: str, question: str) -> bool:
    normalized = f"{title} {question}".lower().replace("-", " ")
    return any(term in normalized for term in ("week five", "week 5", "five week", "dai week 5"))


def _row_style(row: dict[str, Any]) -> dict[str, str] | None:
    row_type = _normalized(row.get("row_type"))
    label = " ".join(
        _normalized(row.get(key)).replace("_", " ")
        for key in ("section", "project_type", "project_name", "label", "name")
        if row.get(key) is not None
    )
    if row_type == "grand_total" or "grand total" in label:
        return _style("grand_total", foreground="#FFFFFF")
    if row_type == "combined_total" or ("cad" in label and "bim" in label and "total" in label):
        return _style("combined_total")
    if row_type == "section_total" or ("total" in label and "grand total" not in label):
        return _style("section_total")
    if row_type == "section_header":
        return _style("section_header")
    return None


def _cell_styles(columns: list[str], row: dict[str, Any]) -> dict[str, dict[str, str]]:
    styles: dict[str, dict[str, str]] = {}
    project_column = _first_column(columns, ("project_name", "project", "project_type"))
    if project_column:
        project_style = _project_style(row)
        if project_style:
            styles[project_column] = project_style

    production_date = _as_date(_first_value(row, ("project_production_date", "production_date")))
    approval_date = _as_date(_first_value(row, ("out_for_approval_date", "approval_date")))
    for column in columns:
        normalized = _normalized(column)
        if _is_week_value_column(normalized):
            week_start, week_end = _week_range(row, normalized)
            value = row.get(column)
            if week_start and week_end and production_date and week_start <= production_date <= week_end:
                styles[column] = _style("production_week")
            elif week_start and week_end and approval_date and week_start <= approval_date <= week_end:
                styles[column] = _style("approval_week")
            elif _numeric(value) > 0:
                styles[column] = _style("task_week")
            else:
                styles[column] = _style("empty_week")
        elif "comment" in normalized and ("status" in normalized or "count" in normalized):
            styles[column] = _comment_style(row.get(column))
        elif "holiday" in normalized and row.get(column):
            styles[column] = {"foreground": "#DC3545", "label": "Holiday"}
    return styles


def _project_style(row: dict[str, Any]) -> dict[str, str] | None:
    has_project_type_id = "project_type_id" in row
    project_type = _normalized(row.get("project_type"))
    if (has_project_type_id and not row.get("project_type_id")) or project_type in {"unassigned", "not started"}:
        return _style("project_not_started", foreground="#DC3545")
    manufacturing_type = _normalized(row.get("project_mfg_type")).replace(" ", "_")
    if manufacturing_type == "cad_cam":
        return _style("project_cad")
    if manufacturing_type == "bim" or row.get("project_type_id") or project_type:
        return _style("project_active", foreground="#FFFFFF")
    return None


def _comment_style(value: Any) -> dict[str, str]:
    normalized = _normalized(value)
    if normalized in {"error", "failed", "unavailable"}:
        return _style("comments_error")
    if _numeric(value) > 0 or normalized in {"yes", "present", "available", "true"}:
        return _style("comments_present", foreground="#FFFFFF")
    return _style("comments_missing", foreground="#FFFFFF")


def _week_range(row: dict[str, Any], normalized_column: str) -> tuple[date | None, date | None]:
    match = re.search(r"(?:week|wk)_?(\d+)", normalized_column)
    if not match:
        return None, None
    number = match.group(1)
    start = _as_date(_first_value(row, (f"week_{number}_start", f"week{number}_start", f"wk_{number}_start")))
    end = _as_date(_first_value(row, (f"week_{number}_end", f"week{number}_end", f"wk_{number}_end")))
    return start, end


def _is_week_value_column(column: str) -> bool:
    return bool(re.search(r"(?:^|_)(?:week|wk)_?\d+(?:$|_(?:tasks?|count)$)", column))


def _first_column(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    normalized = {_normalized(column): column for column in columns}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    return None


def _first_value(row: dict[str, Any], candidates: tuple[str, ...]) -> Any:
    normalized = {_normalized(key): value for key, value in row.items()}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    return None


def _style(key: str, foreground: str = "#111827") -> dict[str, str]:
    return {
        "key": key,
        "background": WEEK_FIVE_PALETTE[key],
        "foreground": foreground,
    }


def _normalized(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _numeric(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text[:10]).date()
    except ValueError:
        return None
