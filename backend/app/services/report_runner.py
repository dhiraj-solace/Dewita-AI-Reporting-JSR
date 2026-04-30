import logging
from app.core.config import get_settings
from app.db import fetch_rows
from app.models import GeneratedReport, ReportRequest
from app.services.date_resolver import resolve_date_range
from app.services.llm import generate_sql_with_ai
from app.services.sql_guard import apply_limit, normalize_live_schema_sql, validate_select_sql
from app.services.templates import find_template

logger = logging.getLogger(__name__)


async def build_report(request: ReportRequest) -> GeneratedReport:
    warnings: list[str] = []
    resolved_dates = resolve_date_range(request.question, request.start_date, request.end_date)
    generated = await generate_sql_with_ai(request.question, resolved_dates.start_date, resolved_dates.end_date)

    if generated is None:
        logger.warning(f"AI SQL generation failed for question: '{request.question}'")
        logger.info("Falling back to template-based report generation")
        
        template = find_template(request.question)
        if template is None:
            logger.warning("No exact template match found, using Project Summary as default")
            template = find_template("project summary")
            warnings.append("No exact report template matched; using Project Summary Report as a safe fallback.")
        else:
            logger.info(f"Using template: '{template.title}' for question: '{request.question}'")
            
        generated = {
            "title": template.title,
            "sql": template.sql,
            "explanation": template.explanation,
        }
        warnings.append(
            "AI SQL generation was unavailable or rejected by the provider, so a safe built-in template was used."
        )
    else:
        logger.info(f"AI SQL generation successful for question: '{request.question}'")

    sql, normalization_warnings = normalize_live_schema_sql(generated["sql"])
    warnings.extend(normalization_warnings)
    sql = validate_select_sql(sql)
    sql = apply_limit(sql, min(request.limit, get_settings().max_rows))
    params = {"start_date": resolved_dates.start_date, "end_date": resolved_dates.end_date}

    columns: list[str] = []
    rows: list[dict] = []
    if not request.dry_run:
        columns, rows = fetch_rows(sql, params)

    return GeneratedReport(
        title=generated["title"],
        question=request.question,
        sql=sql,
        explanation=generated["explanation"],
        assumptions=resolved_dates.assumptions + generated.get("assumptions", []),
        columns=columns,
        rows=rows,
        row_count=len(rows),
        dry_run=request.dry_run,
        warnings=warnings,
    )
