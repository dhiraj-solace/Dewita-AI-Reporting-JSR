from typing import Any

from pydantic import BaseModel, Field


class ReportRequest(BaseModel):
    question: str = Field(..., min_length=3)
    start_date: str | None = None
    end_date: str | None = None
    limit: int = Field(default=100, ge=1, le=1000)
    dry_run: bool = False


class GeneratedReport(BaseModel):
    title: str
    question: str
    sql: str
    explanation: str
    assumptions: list[str] = []
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    dry_run: bool = False
    warnings: list[str] = []
