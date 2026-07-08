import unittest
from datetime import date, timedelta

from app.services.date_resolver import resolve_date_range


class DateResolverTests(unittest.TestCase):
    def test_timesheet_without_dates_defaults_to_last_30_days(self) -> None:
        today = date.today()
        expected_start = today - timedelta(days=29)

        resolved = resolve_date_range("Vinit Thakare timesheet report", None, None, "timesheet")

        self.assertEqual(resolved.start_date, expected_start.isoformat())
        self.assertEqual(resolved.end_date, today.isoformat())
        self.assertTrue(any("last 30 days" in item for item in resolved.assumptions))

    def test_timesheet_default_does_not_override_explicit_month(self) -> None:
        resolved = resolve_date_range("April 2026 timesheet report", None, None, "timesheet")

        self.assertEqual(resolved.start_date, "2026-04-01")
        self.assertEqual(resolved.end_date, "2026-04-30")
        self.assertTrue(any("April 2026" in item for item in resolved.assumptions))

    def test_non_timesheet_without_dates_stays_open_ended(self) -> None:
        resolved = resolve_date_range("Project summary report", None, None, "project")

        self.assertIsNone(resolved.start_date)
        self.assertIsNone(resolved.end_date)
        self.assertEqual(resolved.assumptions, [])


if __name__ == "__main__":
    unittest.main()
