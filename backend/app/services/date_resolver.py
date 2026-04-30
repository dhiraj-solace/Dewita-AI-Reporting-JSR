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


def resolve_date_range(question: str, start_date: str | None, end_date: str | None) -> DateResolution:
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

    return DateResolution(None, None, [])
