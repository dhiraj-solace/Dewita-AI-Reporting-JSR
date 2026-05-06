import re
from dataclasses import dataclass
from typing import Any

from app.services.schema_validator import SchemaValidationError, validate_sql_against_schema
from app.services.sql_guard import FORBIDDEN, validate_select_sql

COMMENT_PATTERN = re.compile(r"(--|#|/\*)")
AGGREGATE_PATTERN = re.compile(r"\b(count|sum|avg|min|max|group_concat)\s*\(", re.IGNORECASE)
LIMIT_PATTERN = re.compile(r"\blimit\s+\d+\s*$", re.IGNORECASE)


@dataclass
class SafetyValidationResult:
    isValid: bool
    reason: str
    fixedSuggestion: str
    riskLevel: str
    mistakeType: str = "unknown"

    def model_dump(self) -> dict[str, str | bool]:
        return {
            "isValid": self.isValid,
            "reason": self.reason,
            "fixedSuggestion": self.fixedSuggestion,
            "riskLevel": self.riskLevel,
            "mistakeType": self.mistakeType,
        }


def validate_sql_safety(sql: str, schema: dict[str, Any], require_limit: bool = True) -> SafetyValidationResult:
    try:
        cleaned = _basic_sql_safety(sql)
        validate_sql_against_schema(cleaned, schema)
        if require_limit and _requires_limit(cleaned) and not LIMIT_PATTERN.search(cleaned):
            return SafetyValidationResult(
                isValid=False,
                reason="Query must include LIMIT unless it is an aggregate/report query.",
                fixedSuggestion="Add a safe LIMIT clause to the query.",
                riskLevel="medium",
                mistakeType="missing_limit",
            )
    except SchemaValidationError as exc:
        message = exc.diagnosis.message
        mistake_type = "invalid_column" if exc.diagnosis.column else "invalid_table"
        return SafetyValidationResult(False, message, "Use only tables and columns from the schema.", "medium", mistake_type)
    except ValueError as exc:
        message = str(exc)
        return SafetyValidationResult(False, message, _suggestion_for_error(message), _risk_for_error(message), _mistake_type(message))
    return SafetyValidationResult(True, "SQL passed local safety validation.", "", "low")


def _basic_sql_safety(sql: str) -> str:
    cleaned = sql.strip()
    if COMMENT_PATTERN.search(cleaned):
        raise ValueError("SQL comments are not allowed because they can hide injection payloads.")
    return validate_select_sql(cleaned)


def _requires_limit(sql: str) -> bool:
    normalized = sql.lower()
    if AGGREGATE_PATTERN.search(normalized):
        return False
    if re.search(r"\bgroup\s+by\b", normalized):
        return False
    return True


def _mistake_type(message: str) -> str:
    lowered = message.lower()
    if "forbidden" in lowered or "write/admin" in lowered:
        return "dangerous_query"
    if "multiple" in lowered:
        return "multiple_statements"
    if "comments" in lowered:
        return "dangerous_query"
    if "only select" in lowered:
        return "dangerous_query"
    if "limit" in lowered:
        return "missing_limit"
    if "syntax" in lowered:
        return "syntax_error"
    return "unknown"


def _risk_for_error(message: str) -> str:
    lowered = message.lower()
    if "forbidden" in lowered or "multiple" in lowered or "comments" in lowered or "only select" in lowered:
        return "high"
    if "limit" in lowered:
        return "medium"
    return "medium"


def _suggestion_for_error(message: str) -> str:
    lowered = message.lower()
    if "limit" in lowered:
        return "Add a safe LIMIT clause for non-aggregate result sets."
    if "multiple" in lowered:
        return "Return exactly one SELECT or WITH query."
    if "comments" in lowered:
        return "Remove SQL comments and return only the query."
    if "only select" in lowered or "forbidden" in lowered:
        return "Return one read-only SELECT or WITH query."
    return "Regenerate a safe SQL query using the provided schema."
