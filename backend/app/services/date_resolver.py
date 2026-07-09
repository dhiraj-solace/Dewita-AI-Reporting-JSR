import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta


MONTHS = {name.lower(): index for index, name in enumerate(calendar.month_name) if name}
MONTHS.update({name.lower(): index for index, name in enumerate(calendar.month_abbr) if name})


@dataclass(frozen=True)
class DateResolution:
    start_date: str | None
    end_date: str | None
    assumptions: list[str]


def resolve_date_range(
    question: str,
    start_date: str | None,
    end_date: str | None,
    report_category_id: str | None = None,
) -> DateResolution:
    if start_date or end_date:
        return DateResolution(start_date, end_date, [])

    normalized = question.lower()
    today = date.today()
    assumptions: list[str] = []

    month_match = re.search(
        r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\s+((?:20)?\d{2})\b",
        normalized,
    )
    if month_match:
        month = MONTHS[month_match.group(1)]
        year = int(month_match.group(2))
        if year < 100:
            year += 2000
        last_day = calendar.monthrange(year, month)[1]
        label = f"{calendar.month_name[month]} {year}"
        assumptions.append(f"Interpreted the requested period as {label}.")
        return DateResolution(f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last_day:02d}", assumptions)

    year_match = re.search(r"\b(?:in|for|during|this)?\s*((?:20)\d{2})\b", normalized)
    if year_match and "month" not in normalized:
        year = int(year_match.group(1))
        assumptions.append(f"Interpreted the requested period as calendar year {year}.")
        return DateResolution(f"{year:04d}-01-01", f"{year:04d}-12-31", assumptions)

    if "this month" in normalized:
        last_day = calendar.monthrange(today.year, today.month)[1]
        assumptions.append(f"Interpreted 'this month' as {calendar.month_name[today.month]} {today.year}.")
        return DateResolution(f"{today.year:04d}-{today.month:02d}-01", f"{today.year:04d}-{today.month:02d}-{last_day:02d}", assumptions)

    if "today" in normalized:
        assumptions.append(f"Interpreted 'today' as {today.isoformat()}.")
        return DateResolution(today.isoformat(), today.isoformat(), assumptions)

    if "yesterday" in normalized:
        yesterday = today - timedelta(days=1)
        assumptions.append(f"Interpreted 'yesterday' as {yesterday.isoformat()}.")
        return DateResolution(yesterday.isoformat(), yesterday.isoformat(), assumptions)

    if "this week" in normalized:
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        assumptions.append(f"Interpreted 'this week' as {week_start.isoformat()} to {week_end.isoformat()}.")
        return DateResolution(week_start.isoformat(), week_end.isoformat(), assumptions)

    if "last week" in normalized:
        this_week_start = today - timedelta(days=today.weekday())
        last_week_start = this_week_start - timedelta(days=7)
        last_week_end = last_week_start + timedelta(days=6)
        assumptions.append(f"Interpreted 'last week' as {last_week_start.isoformat()} to {last_week_end.isoformat()}.")
        return DateResolution(last_week_start.isoformat(), last_week_end.isoformat(), assumptions)

    if "last 30 days" in normalized or "past 30 days" in normalized:
        start = today - timedelta(days=29)
        assumptions.append(f"Interpreted the requested period as the last 30 days ending {today.isoformat()}.")
        return DateResolution(start.isoformat(), today.isoformat(), assumptions)

    if "last month" in normalized:
        first_this_month = today.replace(day=1)
        last_month_end = first_this_month - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        assumptions.append(
            f"Interpreted 'last month' as {calendar.month_name[last_month_start.month]} {last_month_start.year}."
        )
        return DateResolution(last_month_start.isoformat(), last_month_end.isoformat(), assumptions)

    if "this year" in normalized:
        assumptions.append(f"Interpreted 'this year' as calendar year {today.year}.")
        return DateResolution(f"{today.year:04d}-01-01", f"{today.year:04d}-12-31", assumptions)

    if _is_daily_report_request(normalized):
        assumptions.append(f"No date was provided for the daily report, so today ({today.isoformat()}) was used.")
        return DateResolution(today.isoformat(), today.isoformat(), assumptions)

    if _is_timesheet_request(normalized, report_category_id):
        start = today - timedelta(days=29)
        assumptions.append(
            f"No date range was provided for the timesheet report, so the last 30 days "
            f"({start.isoformat()} to {today.isoformat()}) were used."
        )
        return DateResolution(start.isoformat(), today.isoformat(), assumptions)

    return DateResolution(None, None, [])


def _is_timesheet_request(normalized_question: str, report_category_id: str | None) -> bool:
    if str(report_category_id or "").lower() == "timesheet":
        return True
    return any(token in normalized_question for token in ("timesheet", "time sheet", "timelog", "time log"))


def _is_daily_report_request(normalized_question: str) -> bool:
    return any(
        token in normalized_question
        for token in ("daily report", "daily progress", "daily task report", "daily task completion")
    )
