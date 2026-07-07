import unittest

from app.services.catalog import load_schema_catalog
from app.services.sql_safety_validator import validate_sql_safety
from app.services.week_five_report_builder import (
    build_week_five_generated_payload,
    resolve_week_five_intent,
)


class WeekFiveReportBuilderTests(unittest.TestCase):
    def test_resolves_bim_team_leader_comments_and_grand_total_intent(self) -> None:
        intent = resolve_week_five_intent(
            "Show week 5 report for BIM projects by team leader with project task comments and grand total"
        )

        self.assertEqual(intent.manufacturing_type, "BIM")
        self.assertTrue(intent.group_by_team_leader)
        self.assertTrue(intent.include_project_task_comments)
        self.assertTrue(intent.include_section_totals)
        self.assertTrue(intent.include_grand_total)

    def test_plain_week_five_includes_section_and_grand_totals(self) -> None:
        generated = build_week_five_generated_payload("Show week 5 report")

        self.assertIsNotNone(generated)
        sql = generated["sql"]
        self.assertIn("p.project_mfg_type IN ('CAD_CAM', 'BIM')", sql)
        self.assertIn("COALESCE(p.client, '') = 'DAI'", sql)
        self.assertIn("'section_total' AS row_type", sql)
        self.assertIn("Total (BIM)", sql)
        self.assertIn("Total (CAD)", sql)
        self.assertIn("'grand_total' AS row_type", sql)
        self.assertNotIn("COALESCE(p.client, '') != 'DAI'", sql)

        safety = validate_sql_safety(sql, load_schema_catalog())
        self.assertTrue(safety.isValid, safety.reason)

    def test_builds_schema_valid_bim_week_five_sql(self) -> None:
        generated = build_week_five_generated_payload(
            "Show week 5 report for BIM projects by team leader with project task comments and grand total"
        )

        self.assertIsNotNone(generated)
        sql = generated["sql"]
        self.assertIn("p.project_mfg_type = 'BIM'", sql)
        self.assertIn("daily_project_comments", sql)
        self.assertIn("'team_leader_total' AS row_type", sql)
        self.assertIn("'section_total' AS row_type", sql)
        self.assertIn("'grand_total' AS row_type", sql)
        self.assertIn("FROM project_rows", sql)
        self.assertNotIn("timelog_records.is_deleted", sql)

        safety = validate_sql_safety(sql, load_schema_catalog())
        self.assertTrue(safety.isValid, safety.reason)


if __name__ == "__main__":
    unittest.main()
