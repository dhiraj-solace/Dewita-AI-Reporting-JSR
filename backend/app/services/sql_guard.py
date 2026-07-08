import re

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|call|execute|merge)\b",
    re.IGNORECASE,
)

def normalize_live_schema_sql(sql: str) -> tuple[str, list[str]]:
    """Repair common AI SQL drift against the live Devita schema."""
    warnings: list[str] = []
    normalized = sql
    normalized = _normalize_attendance_sql(normalized, warnings)
    normalized = _normalize_date_parameter_drift(normalized, warnings)
    
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

        before_role_type = normalized
        normalized = re.sub(
            rf"\b`?{re.escape(alias)}`?\.role_type\b",
            f"{alias}.user_type",
            normalized,
            flags=re.IGNORECASE,
        )
        if normalized != before_role_type:
            warnings.append("Rewrote timelog_records.role_type to timelog_records.user_type from the live schema.")

        before_deleted_filter = normalized
        normalized = re.sub(
            rf"\bCOALESCE\s*\(\s*`?{re.escape(alias)}`?\.is_deleted\s*,\s*0\s*\)\s*=\s*0\b",
            "1=1",
            normalized,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(
            rf"\b`?{re.escape(alias)}`?\.is_deleted\s*(?:=|<>|!=)\s*[01]\b",
            "1=1",
            normalized,
            flags=re.IGNORECASE,
        )
        if normalized != before_deleted_filter:
            warnings.append(
                "Removed invalid timelog_records.is_deleted filter because the live table has no is_deleted column."
            )

    before_team_leader_json = normalized
    normalized = re.sub(
        r"JSON_CONTAINS\s*\(\s*"
        r"(?P<team_leader>(?:`?[A-Za-z_][\w]*`?\.)?`?team_leader`?)\s*,\s*"
        r"CAST\s*\(\s*(?P<user_id>`?[A-Za-z_][\w]*`?\.`?id`?)\s+AS\s+JSON\s*\)\s*"
        r"\)",
        lambda match: (
            f"FIND_IN_SET(CAST({match.group('user_id')} AS CHAR), "
            f"REPLACE(REPLACE(REPLACE(COALESCE({match.group('team_leader')}, ''), '[', ''), ']', ''), '\"', '')) > 0"
        ),
        normalized,
        flags=re.IGNORECASE,
    )
    if normalized != before_team_leader_json:
        warnings.append("Rewrote JSON_CONTAINS team_leader matching to MariaDB-compatible FIND_IN_SET logic.")

    return normalized, warnings


def _normalize_date_parameter_drift(sql: str, warnings: list[str]) -> str:
    normalized = sql
    before = normalized
    normalized = re.sub(r"(?<![:.`\w])start_date(?![`.\w])", "NULL", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"(?<![:.`\w])end_date(?![`.\w])", "NULL", normalized, flags=re.IGNORECASE)
    if normalized != before:
        warnings.append(
            "Rewrote bare start_date/end_date parameter names to NULL so they are not treated as database columns."
        )
    return normalized


def _normalize_attendance_sql(sql: str, warnings: list[str]) -> str:
    normalized = sql
    attendance_aliases = {
        match.group("alias") or "attendances"
        for match in re.finditer(
            r"\b(?:from|join)\s+`?attendances`?(?:\s+(?:as\s+)?`?(?P<alias>[A-Za-z_][\w]*)`?)?",
            normalized,
            re.IGNORECASE,
        )
    }
    if re.search(r"\b(?:from|join)\s+`?attendances`?\b", normalized, re.IGNORECASE):
        attendance_aliases.add("attendances")

    for alias in attendance_aliases:
        before = normalized
        normalized = re.sub(
            rf"\bTIMEDIFF\s*\(\s*`?{re.escape(alias)}`?\.check_out\s*,\s*`?{re.escape(alias)}`?\.check_in\s*\)",
            f"{alias}.total_hours",
            normalized,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(
            rf"\bTIMESTAMPDIFF\s*\(\s*HOUR\s*,\s*`?{re.escape(alias)}`?\.check_in\s*,\s*`?{re.escape(alias)}`?\.check_out\s*\)",
            f"{alias}.total_hours",
            normalized,
            flags=re.IGNORECASE,
        )
        if normalized != before:
            warnings.append(
                "Rewrote attendance check-in/check-out duration to attendances.total_hours from the live schema."
            )

        before_user_id = normalized
        normalized = re.sub(
            rf"\b`?{re.escape(alias)}`?\.user_id\b",
            f"{alias}.employee_id",
            normalized,
            flags=re.IGNORECASE,
        )
        if normalized != before_user_id:
            warnings.append("Rewrote attendances.user_id to attendances.employee_id from the live schema.")

        before_punch_columns = normalized
        normalized = re.sub(
            rf"\b`?{re.escape(alias)}`?\.check_in\b",
            "NULL",
            normalized,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(
            rf"\b`?{re.escape(alias)}`?\.check_out\b",
            "NULL",
            normalized,
            flags=re.IGNORECASE,
        )
        if normalized != before_punch_columns:
            warnings.append(
                "Replaced unavailable attendance check_in/check_out columns with NULL because the live table exposes total_hours instead."
            )

    return normalized


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
