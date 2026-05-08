import re
from dataclasses import dataclass


WRITE_OPERATION_PATTERN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|merge|replace|call|exec|execute)\b",
    re.IGNORECASE,
)
READ_OPERATION_PATTERN = re.compile(
    r"\b(select|show|list|get|fetch|find|view|display|report|summary|count|sum|average|avg|total|totals)\b",
    re.IGNORECASE,
)
RAW_SQL_START_PATTERN = re.compile(r"^\s*(with|select|insert|update|delete|drop|alter|truncate|create)\b", re.IGNORECASE)


@dataclass
class QuerySafetyResult:
    is_safe: bool
    reason: str = ""
    blocked_operation: str | None = None


def validate_user_query_safety(query: str) -> QuerySafetyResult:
    """Cheap first-pass safety check that inspects only the user query text."""
    normalized = " ".join(query.strip().split())
    if not normalized:
        return QuerySafetyResult(False, "Question is empty.")

    raw_sql_match = RAW_SQL_START_PATTERN.search(normalized)
    if raw_sql_match and raw_sql_match.group(1).lower() not in {"select", "with"}:
        operation = raw_sql_match.group(1).upper()
        return QuerySafetyResult(
            False,
            f"{operation} is not allowed. Only read-only reporting requests are supported.",
            operation,
        )

    write_match = WRITE_OPERATION_PATTERN.search(normalized)
    if write_match:
        operation = write_match.group(1).upper()
        return QuerySafetyResult(
            False,
            f"{operation} is not allowed. Ask for a read-only report instead.",
            operation,
        )

    if raw_sql_match and raw_sql_match.group(1).lower() in {"select", "with"}:
        return QuerySafetyResult(True)

    if READ_OPERATION_PATTERN.search(normalized):
        return QuerySafetyResult(True)

    return QuerySafetyResult(
        False,
        "Only read-only reporting questions are supported. Ask for a report, list, count, total, or summary.",
    )
