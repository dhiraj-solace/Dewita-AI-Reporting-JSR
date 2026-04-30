import re

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|call|execute|merge)\b",
    re.IGNORECASE,
)

def normalize_live_schema_sql(sql: str) -> tuple[str, list[str]]:
    """Repair common AI SQL drift against the live Devita schema."""
    warnings: list[str] = []
    normalized = sql
    
    timelog_aliases = {
        match.group("alias") or "timelog_records"
        for match in re.finditer(
            r"\b(?:from|join)\s+`?timelog_records`?(?:\s+(?:as\s+)?`?(?P<alias>[A-Za-z_][\w]*)`?)?",
            normalized,
            re.IGNORECASE,
        )
    }
    if re.search(r"\b(?:from|join)\s+`?timelog_records`?\b", normalized, re.IGNORECASE):
        timelog_aliases.add("timelog_records")

    for alias in timelog_aliases:
        duration = f"(COALESCE({alias}.hours, 0) + (COALESCE({alias}.minutes, 0) / 60))"
        before = normalized
        normalized = re.sub(
            rf"\bSUM\s*\(\s*`?{re.escape(alias)}`?\.time_spent\s*\)",
            f"SUM({duration})",
            normalized,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(
            rf"\b`?{re.escape(alias)}`?\.time_spent\b",
            duration,
            normalized,
            flags=re.IGNORECASE,
        )
        if normalized != before:
            warnings.append(
                "Rewrote timelog_records.time_spent to the live hours/minutes duration expression."
            )

    return normalized, warnings


def validate_select_sql(sql: str) -> str:
    cleaned = sql.strip().rstrip(";")
    if not re.match(r"^(select|with)\b", cleaned, re.IGNORECASE):
        raise ValueError("Only SELECT/CTE report queries are allowed.")
    if FORBIDDEN.search(cleaned):
        raise ValueError("The generated SQL contains a forbidden write/admin statement.")
    if ";" in cleaned:
        raise ValueError("Multiple SQL statements are not allowed.")
    return cleaned


def apply_limit(sql: str, limit: int) -> str:
    if re.search(r"\blimit\s+\d+\s*$", sql, re.IGNORECASE):
        return sql
    return f"{sql}\nLIMIT {limit}"
