from typing import Any

from pydantic import BaseModel, Field


class ReportRequest(BaseModel):
    question: str = Field(..., min_length=3)
    report_category: str | None = None
    current_user_role: str | None = "Super Admin"
    start_date: str | None = None
    end_date: str | None = None
    limit: int = Field(default=100, ge=1, le=1000)
    dry_run: bool = False
    sql_generation_provider: str | None = Field(default=None, pattern="^(openrouter|ollama|gemini|openai)$")


class RetryAttempt(BaseModel):
    attempt: int
    status: str
    message: str
    sql: str | None = None
    schema_issue: str | None = None


class ValidationErrorItem(BaseModel):
    type: str
    message: str
    fix_hint: str


class ValidationResult(BaseModel):
    is_valid: bool
    reason: str = ""
    errors: list[ValidationErrorItem] = []
    retry_prompt: str = ""


class GeneratedReport(BaseModel):
    attempt_id: str | None = None
    saved_report_id: str | None = None
    generated_source: str | None = None
    report_category: str | None = None
    created_by_role: str | None = None
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


class SavedReportSummary(BaseModel):
    id: str
    title: str
    question: str
    report_category: str | None = None
    created_by_role: str | None = None
    row_count: int
    created_at: Any


class RoleReportPermission(BaseModel):
    role_name: str
    report_category: str
    can_view: bool = False
    can_create: bool = False
    can_export: bool = False
    can_save: bool = False
    can_view_saved: bool = False
    data_scope: str = Field(default="self", pattern="^(all|role|team|project|self|none)$")


class RoleReportPermissionsPayload(BaseModel):
    permissions: list[RoleReportPermission]


class ScheduledReportBase(BaseModel):
    name: str = Field(..., min_length=2)
    report_category: str = "custom"
    question: str = Field(..., min_length=3)
    frequency: str = Field(..., pattern="^(daily|weekly|monthly)$")
    schedule_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    timezone: str = "Asia/Calcutta"
    filters: dict[str, Any] = {}
    recipients: dict[str, Any] = {}
    current_user_role: str = "Super Admin"
    sql_generation_provider: str | None = Field(default=None, pattern="^(openrouter|ollama|gemini|openai)$")
    limit: int = Field(default=500, ge=1, le=1000)
    dry_run: bool = False
    export_formats: list[str] = []
    execution_settings: dict[str, Any] = {}
    is_active: bool = True


class ScheduledReportCreate(ScheduledReportBase):
    pass


class ScheduledReportUpdate(ScheduledReportBase):
    pass


class ScheduledReport(ScheduledReportBase):
    id: str
    next_run_at: Any | None = None
    last_run_at: Any | None = None
    last_status: str | None = None
    last_error: str | None = None
    created_by_role: str | None = None
    created_at: Any
    updated_at: Any


class ScheduledReportRun(BaseModel):
    id: str
    scheduled_report_id: str
    saved_report_id: str | None = None
    status: str
    started_at: Any | None = None
    finished_at: Any | None = None
    error_message: str | None = None
    generated_row_count: int | None = None
    metadata_json: str | None = None


class ReportAuditLog(BaseModel):
    id: str
    event_type: str
    actor_role: str | None = None
    target_role: str | None = None
    report_id: str | None = None
    report_category: str | None = None
    action: str | None = None
    before_json: str | None = None
    after_json: str | None = None
    metadata_json: str | None = None
    created_at: Any


class AiSqlAttempt(BaseModel):
    id: str
    user_question: str
    schema_snapshot: str | None = None
    generation_provider: str | None = None
    generation_model: str | None = None
    generation_elapsed_ms: int | None = None
    validator_elapsed_ms: int | None = None
    execution_elapsed_ms: int | None = None
    total_elapsed_ms: int | None = None
    generated_sql: str | None = None
    validator_status: str | None = None
    validator_feedback: str | None = None
    regenerated_sql: str | None = None
    final_sql: str | None = None
    execution_status: str | None = None
    execution_error: str | None = None
    result_row_count: int | None = None
    user_feedback_status: str | None = None
    admin_approved: bool = False
    is_gold_example: bool = False
    created_at: Any
    updated_at: Any


class AiSqlAttemptReviewRequest(BaseModel):
    user_feedback_status: str = Field(..., pattern="^(pending|correct|incorrect)$")
    admin_approved: bool = False


class SqlMistakeExample(BaseModel):
    id: str
    query_attempt_id: str
    user_question: str
    wrong_sql: str | None = None
    validator_feedback: str | None = None
    validation_reason: str | None = None
    mistake_type: str
    corrected_sql: str | None = None
    final_correct_sql: str | None = None
    risk_level: str
    created_at: Any


class AiSqlAttemptPreview(BaseModel):
    attempt_id: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    preview_limit: int
    execution_status: str
    error: str | None = None
