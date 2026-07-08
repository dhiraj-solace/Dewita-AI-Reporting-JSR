import unittest

from app.services.catalog import load_schema_catalog
from app.services.sql_safety_validator import validate_sql_safety
from app.services.templates import find_template


class AttendanceTemplateTests(unittest.TestCase):
    def test_attendance_template_uses_live_total_hours_schema(self) -> None:
        template = find_template("Attendance Report", "attendance")

        self.assertIsNotNone(template)
        sql = template.sql
        self.assertIn("a.total_hours AS work_hours", sql)
        self.assertIn("a.employee_id", sql)
        self.assertIn("u.employee_id = a.employee_id", sql)
        self.assertNotIn("a.check_in", sql)
        self.assertNotIn("a.check_out", sql)
        self.assertNotIn("a.user_id", sql)

        safety = validate_sql_safety(sql, load_schema_catalog(), require_limit=False)
        self.assertTrue(safety.isValid, safety.reason)


if __name__ == "__main__":
    unittest.main()
