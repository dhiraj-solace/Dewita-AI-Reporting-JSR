import smtplib
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any

from app.core.config import get_settings
from app.models import GeneratedReport
from app.services.report_exporter import export_filename, export_report_pdf, export_report_xlsx


def is_email_configured() -> bool:
    settings = get_settings()
    return bool(settings.smtp_host and settings.smtp_from_email)


def send_report_email(
    report: GeneratedReport,
    recipients: list[str],
    formats: list[str] | None = None,
) -> dict[str, Any]:
    cleaned_recipients = _clean_recipients(recipients)
    if not cleaned_recipients:
        return {"status": "skipped", "reason": "No recipient emails configured."}
    if not is_email_configured():
        return {"status": "skipped", "reason": "SMTP settings are not configured."}

    settings = get_settings()
    attachments = _build_attachments(report, formats or ["xlsx"])
    message = EmailMessage()
    message["Subject"] = f"[Devita AI Reporting] {report.title}"
    message["From"] = formataddr((settings.smtp_from_name, settings.smtp_from_email or ""))
    message["To"] = ", ".join(cleaned_recipients)
    message.set_content(_email_body(report, attachments))

    for attachment in attachments:
        message.add_attachment(
            attachment["content"],
            maintype=attachment["maintype"],
            subtype=attachment["subtype"],
            filename=attachment["filename"],
        )

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username and settings.smtp_password:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    except Exception as exc:
        return {
            "status": "failed",
            "reason": str(exc),
            "recipients": cleaned_recipients,
            "attachments": [item["filename"] for item in attachments],
        }

    return {
        "status": "sent",
        "recipients": cleaned_recipients,
        "attachments": [item["filename"] for item in attachments],
    }


def _build_attachments(report: GeneratedReport, formats: list[str]) -> list[dict[str, Any]]:
    attachments = []
    normalized_formats = {str(item).strip().lower() for item in formats if str(item).strip()}
    if not normalized_formats:
        normalized_formats = {"xlsx"}
    if "pdf" in normalized_formats:
        attachments.append(
            {
                "filename": export_filename(report, "pdf"),
                "content": export_report_pdf(report),
                "maintype": "application",
                "subtype": "pdf",
            }
        )
    if "xlsx" in normalized_formats or "excel" in normalized_formats:
        attachments.append(
            {
                "filename": export_filename(report, "xlsx"),
                "content": export_report_xlsx(report),
                "maintype": "application",
                "subtype": "vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }
        )
    return attachments


def _email_body(report: GeneratedReport, attachments: list[dict[str, Any]]) -> str:
    attachment_names = ", ".join(item["filename"] for item in attachments) or "none"
    return "\n".join(
        [
            "A scheduled Devita AI report has been generated.",
            "",
            f"Report: {report.title}",
            f"Category: {report.report_category or 'custom'}",
            f"Rows: {report.row_count}",
            f"Saved report ID: {report.saved_report_id or 'not saved'}",
            f"Attachments: {attachment_names}",
            "",
            "This is an automated notification from Devita AI Reporting.",
        ]
    )


def _clean_recipients(recipients: list[str]) -> list[str]:
    seen = set()
    cleaned = []
    for recipient in recipients:
        email = str(recipient or "").strip()
        if not email or email.lower() in seen:
            continue
        seen.add(email.lower())
        cleaned.append(email)
    return cleaned
