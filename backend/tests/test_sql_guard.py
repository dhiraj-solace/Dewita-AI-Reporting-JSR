import unittest

from app.services.sql_guard import normalize_live_schema_sql


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


if __name__ == "__main__":
    unittest.main()
