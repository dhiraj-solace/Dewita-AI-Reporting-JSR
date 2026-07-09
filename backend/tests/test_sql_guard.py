import unittest

from app.services.catalog import load_schema_catalog
from app.services.sql_guard import normalize_live_schema_sql
from app.services.sql_safety_validator import validate_sql_safety


class SqlGuardTests(unittest.TestCase):
    def test_removes_invalid_timelog_is_deleted_filter(self) -> None:
        sql = """
SELECT tr.project_id, SUM(tr.hours) AS hours
FROM timelog_records tr
WHERE tr.is_deleted = 0
GROUP BY tr.project_id
        """.strip()

        normalized, warnings = normalize_live_schema_sql(sql)

        self.assertNotIn("tr.is_deleted", normalized)
        self.assertIn("WHERE 1=1", normalized)
        self.assertIn("Removed invalid timelog_records.is_deleted filter", " ".join(warnings))

    def test_removes_invalid_timelog_coalesce_deleted_filter(self) -> None:
        sql = """
SELECT tr.project_id
FROM timelog_records AS tr
WHERE COALESCE(tr.is_deleted, 0) = 0
        """.strip()

        normalized, warnings = normalize_live_schema_sql(sql)

        self.assertNotIn("tr.is_deleted", normalized)
        self.assertIn("WHERE 1=1", normalized)
        self.assertTrue(any("timelog_records.is_deleted" in warning for warning in warnings))

    def test_rewrites_attendance_check_in_out_drift(self) -> None:
        sql = """
SELECT
  u.id AS user_id,
  u.name AS employee_name,
  a.date,
  a.status,
  a.check_in,
  a.check_out,
  TIMEDIFF(a.check_out, a.check_in) AS work_hours
FROM attendances a
LEFT JOIN users u ON u.id = a.user_id
ORDER BY a.date DESC
LIMIT 100
        """.strip()

        normalized, warnings = normalize_live_schema_sql(sql)

        self.assertNotIn("a.check_in", normalized)
        self.assertNotIn("a.check_out", normalized)
        self.assertNotIn("a.user_id", normalized)
        self.assertIn("a.total_hours AS work_hours", normalized)
        self.assertIn("a.employee_id", normalized)
        self.assertTrue(any("attendance check-in/check-out" in warning for warning in warnings))

        safety = validate_sql_safety(normalized, load_schema_catalog())
        self.assertTrue(safety.isValid, safety.reason)

    def test_rewrites_timelog_role_type_drift(self) -> None:
        sql = """
SELECT
  tr.date,
  tr.role_type,
  tr.time_spent AS total_hours
FROM timelog_records tr
ORDER BY tr.date DESC
LIMIT 100
        """.strip()

        normalized, warnings = normalize_live_schema_sql(sql)

        self.assertNotIn("tr.role_type", normalized)
        self.assertNotIn("tr.time_spent", normalized)
        self.assertIn("tr.user_type", normalized)
        self.assertIn("COALESCE(tr.hours, 0)", normalized)
        self.assertTrue(any("timelog_records.role_type" in warning for warning in warnings))

        safety = validate_sql_safety(normalized, load_schema_catalog())
        self.assertTrue(safety.isValid, safety.reason)

    def test_rewrites_bare_date_parameter_drift(self) -> None:
        sql = """
SELECT
  tr.date,
  SUM(COALESCE(tr.hours, 0) + (COALESCE(tr.minutes, 0) / 60)) AS total_hours
FROM timelog_records tr
WHERE (start_date IS NULL OR tr.date >= start_date)
  AND (end_date IS NULL OR tr.date <= end_date)
GROUP BY tr.date
ORDER BY tr.date DESC
LIMIT 100
        """.strip()

        normalized, warnings = normalize_live_schema_sql(sql)

        self.assertNotIn("start_date", normalized)
        self.assertNotIn("end_date", normalized)
        self.assertIn("NULL IS NULL", normalized)
        self.assertTrue(any("start_date/end_date" in warning for warning in warnings))

        safety = validate_sql_safety(normalized, load_schema_catalog())
        self.assertTrue(safety.isValid, safety.reason)


if __name__ == "__main__":
    unittest.main()
