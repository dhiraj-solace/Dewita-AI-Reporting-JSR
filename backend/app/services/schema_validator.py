import re
from dataclasses import dataclass
from difflib import get_close_matches
from typing import Any


TABLE_REF = re.compile(
    r"\b(?:from|join)\s+`?(?P<table>[A-Za-z_][\w]*)`?(?:\s+(?:as\s+)?`?(?P<alias>[A-Za-z_][\w]*)`?)?",
    re.IGNORECASE,
)
COLUMN_REF = re.compile(r"\b`?(?P<alias>[A-Za-z_][\w]*)`?\.`?(?P<column>[A-Za-z_][\w]*)`?")
UNKNOWN_COLUMN = re.compile(r"Unknown column '([^']+)'", re.IGNORECASE)
UNKNOWN_TABLE = re.compile(r"Table '[^']*\.([^']+)' doesn't exist", re.IGNORECASE)
SQL_KEYWORDS = {
    "where",
    "left",
    "right",
    "inner",
    "outer",
    "full",
    "join",
    "on",
    "group",
    "order",
    "limit",
    "having",
    "union",
}


@dataclass
class SchemaDiagnosis:
    message: str
    table: str | None = None
    column: str | None = None
    suggestion: str | None = None


class SchemaValidationError(ValueError):
    def __init__(self, diagnosis: SchemaDiagnosis):
        super().__init__(diagnosis.message)
        self.diagnosis = diagnosis


def build_schema_index(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    tables = schema.get("tables") if isinstance(schema, dict) else None
    if not isinstance(tables, list):
        return {}

    index: dict[str, dict[str, Any]] = {}
    for table in tables:
        if not isinstance(table, dict) or not table.get("name"):
            continue
        columns = table.get("columns") if isinstance(table.get("columns"), list) else []
        column_names = {
            column.get("name")
            for column in columns
            if isinstance(column, dict) and isinstance(column.get("name"), str)
        }
        entry = {
            "name": table["name"],
            "columns": {name.lower(): name for name in column_names if name},
        }
        index[table["name"].lower()] = entry
        for alias in table.get("aliases", []) or []:
            if isinstance(alias, str):
                index[alias.lower()] = entry
    return index


def validate_schema_catalog(schema: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    tables = schema.get("tables") if isinstance(schema, dict) else None
    if not isinstance(tables, list) or not tables:
        raise SchemaValidationError(
            SchemaDiagnosis("Schema metadata is missing tables; using fallback metadata if available.")
        )

    seen: set[str] = set()
    for table in tables:
        name = table.get("name") if isinstance(table, dict) else None
        if not isinstance(name, str) or not name.strip():
            warnings.append("Skipped a schema table with a missing name.")
            continue
        normalized = name.lower()
        if normalized in seen:
            warnings.append(f"Duplicate schema metadata found for table `{name}`.")
        seen.add(normalized)

        columns = table.get("columns") if isinstance(table.get("columns"), list) else []
        if not columns:
            warnings.append(f"Table `{name}` has no column metadata; column checks may be partial.")
    return warnings


def validate_sql_against_schema(sql: str, schema: dict[str, Any]) -> list[str]:
    warnings = validate_schema_catalog(schema)
    index = build_schema_index(schema)
    if not index:
        return warnings + ["Schema index is empty; skipped SQL schema validation."]

    alias_to_table: dict[str, str] = {}
    for match in TABLE_REF.finditer(sql):
        table = match.group("table")
        alias = match.group("alias") or table
        if alias.lower() in SQL_KEYWORDS:
            alias = table
        entry = index.get(table.lower())
        if entry is None:
            raise SchemaValidationError(_diagnose_missing_table(table, index))
        alias_to_table[alias.lower()] = entry["name"]
        alias_to_table[table.lower()] = entry["name"]

    for match in COLUMN_REF.finditer(sql):
        alias = match.group("alias")
        column = match.group("column")
        table_name = alias_to_table.get(alias.lower())
        if not table_name:
            continue
        entry = index.get(table_name.lower())
        if entry and column.lower() not in entry["columns"]:
            raise SchemaValidationError(_diagnose_missing_column(column, table_name, entry, index))

    return warnings


def diagnose_database_error(error: Exception, schema: dict[str, Any]) -> SchemaDiagnosis | None:
    message = str(error)
    index = build_schema_index(schema)

    column_match = UNKNOWN_COLUMN.search(message)
    if column_match:
        raw = column_match.group(1)
        if "." in raw:
            table_or_alias, column = raw.split(".", 1)
        else:
            table_or_alias, column = None, raw

        if table_or_alias:
            table_entry = index.get(table_or_alias.lower())
            if table_entry:
                return _diagnose_missing_column(column, table_entry["name"], table_entry, index)
        return SchemaDiagnosis(
            message=f"Column `{raw}` was rejected by the database and could not be matched in schema metadata.",
            column=raw,
        )

    table_match = UNKNOWN_TABLE.search(message)
    if table_match:
        return _diagnose_missing_table(table_match.group(1), index)

    return None


def _diagnose_missing_table(table: str, index: dict[str, dict[str, Any]]) -> SchemaDiagnosis:
    known_tables = sorted({entry["name"] for entry in index.values()})
    suggestion = _best_match(table, known_tables)
    message = f"Table `{table}` is not present in the current schema metadata."
    if suggestion:
        message += f" Did you mean `{suggestion}`?"
    return SchemaDiagnosis(message=message, table=table, suggestion=suggestion)


def _diagnose_missing_column(
    column: str,
    table: str,
    entry: dict[str, Any],
    index: dict[str, dict[str, Any]],
) -> SchemaDiagnosis:
    known_columns = sorted(entry["columns"].values())
    suggestion = _best_match(column, known_columns)
    message = f"Column `{column}` does not exist on table `{table}`."
    if suggestion:
        message += f" Did you mean `{table}.{suggestion}`?"
    else:
        column_locations = _find_column_locations(column, index, exclude_table=table)
        if column_locations:
            suggestion = column_locations[0]
            locations = ", ".join(column_locations[:5])
            message += f" Column `{column}` exists on: {locations}."
    return SchemaDiagnosis(message=message, table=table, column=column, suggestion=suggestion)


def _best_match(value: str, candidates: list[str]) -> str | None:
    matches = get_close_matches(value, candidates, n=1, cutoff=0.6)
    return matches[0] if matches else None


def _find_column_locations(
    column: str,
    index: dict[str, dict[str, Any]],
    exclude_table: str | None = None,
) -> list[str]:
    locations: set[str] = set()
    for entry in index.values():
        table_name = entry["name"]
        if exclude_table and table_name.lower() == exclude_table.lower():
            continue
        actual_column = entry["columns"].get(column.lower())
        if actual_column:
            locations.add(f"{table_name}.{actual_column}")
    return sorted(locations)
