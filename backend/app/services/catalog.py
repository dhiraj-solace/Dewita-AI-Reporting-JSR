import json
from functools import lru_cache
from pathlib import Path
from typing import Any

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


def catalog_context() -> str:
    schema = load_schema_catalog()
    reports = load_report_catalog()
    tables = []
    for table in schema["tables"]:
        columns = ", ".join(column["name"] for column in table["columns"])
        aliases = f" aliases={table.get('aliases', [])}" if table.get("aliases") else ""
        tables.append(f"- {table['name']}{aliases}: {columns}")
    report_lines = []
    for report in reports["reports"]:
        report_lines.append(
            f"- {report['name']}: tables={', '.join(report['tables'])}; metrics={'; '.join(report['metrics'])}"
        )
    return "SCHEMA\n" + "\n".join(tables) + "\n\nREPORTS\n" + "\n".join(report_lines)
