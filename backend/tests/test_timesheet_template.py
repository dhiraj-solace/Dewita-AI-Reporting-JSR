import unittest

from app.services.catalog import load_schema_catalog
from app.services.catalog import resolve_report_category
from app.services.sql_safety_validator import validate_sql_safety
from app.services.templates import find_template


class TimesheetTemplateTests(unittest.TestCase):
    def test_team_timesheet_template_uses_live_timelog_schema(self) -> None:
        template = find_template("Hr timesheet report", "timesheet")

        self.assertIsNotNone(template)
        sql = template.sql
        self.assertIn("tr.user_type", sql)
        self.assertIn("COALESCE(tr.hours, 0)", sql)
        self.assertIn("COALESCE(tr.minutes, 0)", sql)
        self.assertIn("non_billable_hours", sql)
        self.assertIn("YEARWEEK(tr.date, 1)", sql)
        self.assertNotIn("tr.role_type", sql)
        self.assertNotIn("tr.time_spent", sql)
        self.assertNotIn("clarification_needed", sql)

        safety = validate_sql_safety(sql, load_schema_catalog(), require_limit=False)
        self.assertTrue(safety.isValid, safety.reason)

    def test_timesheet_category_uses_user_type_filter(self) -> None:
        category = resolve_report_category("timesheet", "Vinit Thakare timesheet report")

        self.assertIsNotNone(category)
        self.assertIn("user_type", category["filters"])
        self.assertNotIn("role_type", category["filters"])


if __name__ == "__main__":
    unittest.main()
