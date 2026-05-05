import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings
from app.models import ReportFeedbackRequest, ReportFeedbackResponse

FEEDBACK_PATH = Path(__file__).resolve().parents[1] / "data" / "report_feedback.jsonl"


def save_report_feedback(feedback: ReportFeedbackRequest) -> ReportFeedbackResponse:
    feedback_id = str(uuid4())
    record = {
        "id": feedback_id,
        "created_at": datetime.now(UTC).isoformat(),
        "environment": get_settings().environment,
        "ai_provider": get_settings().ai_provider,
        "model": _current_model_name(),
        "review_status": "new",
        **feedback.model_dump(),
    }
    FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with FEEDBACK_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")
    return ReportFeedbackResponse(
        id=feedback_id,
        status="saved",
        message="Feedback saved for review.",
    )


def _current_model_name() -> str:
    settings = get_settings()
    provider = settings.ai_provider.lower()
    if provider == "openrouter":
        return settings.openrouter_model
    if provider == "gemini":
        return settings.gemini_model
    return settings.openai_model
