from typing import Any

from pydantic import BaseModel, Field


class ReportRequest(BaseModel):
    question: str = Field(..., min_length=3)
    start_date: str | None = None
    end_date: str | None = None
    limit: int = Field(default=100, ge=1, le=1000)
    dry_run: bool = False


class RetryAttempt(BaseModel):
    attempt: int
    status: str
    message: str
    sql: str | None = None
    schema_issue: str | None = None


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
    retry_attempts: list[RetryAttempt] = []


class ReportFeedbackRequest(BaseModel):
    question: str = Field(..., min_length=3)
    report_title: str | None = None
    generated_sql: str | None = None
    rating: str = Field(..., pattern="^(up|down)$")
    reason: str | None = None
    comment: str | None = None
    expected_result: str | None = None
    corrected_sql: str | None = None
    retry_attempts: list[RetryAttempt] = []
    warnings: list[str] = []
    row_count: int | None = None


class ReportFeedbackResponse(BaseModel):
    id: str
    status: str
    message: str
