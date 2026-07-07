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

    def test_resolves_cad_cam_project_product_breakdown_intent(self) -> None:
        intent = resolve_week_five_intent(
            "For the Week 5 report, show details for each Cad cam project with products, shop tickets, team members, kickoff, priority, and completed yesterday"
        )

        self.assertEqual(intent.manufacturing_type, "CAD_CAM")
        self.assertTrue(intent.detailed_project_product_breakdown)

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

    def test_builds_schema_valid_cad_cam_project_product_breakdown_sql(self) -> None:
        generated = build_week_five_generated_payload(
            "For the Week 5 report, the following details should be displayed for each Cad cam project: "
            "Project name, Team Leader and assigned Team Members, Products associated with each project, "
            "Number of shop tickets for each product, Project kickoff date, Project priority, MFG type, "
            "Total number of planned tasks, Number of shop tickets/tasks uploaded and completed yesterday"
        )

        self.assertIsNotNone(generated)
        sql = generated["sql"]
        self.assertIn("'project_product_detail' AS row_type", sql)
        self.assertIn("p.project_mfg_type = 'CAD_CAM'", sql)
        self.assertIn("products prod", sql)
        self.assertIn("product_task_details ptd", sql)
        self.assertIn("task.assign_member", sql)
        self.assertIn("p.kick_off_meeting_date AS project_kickoff_date", sql)
        self.assertIn("p.priority AS project_priority", sql)
        self.assertIn("uploaded_yesterday_tasks", sql)
        self.assertIn("completed_yesterday_tasks", sql)
        self.assertNotIn("'section_total' AS row_type", sql)
        self.assertNotIn("'grand_total' AS row_type", sql)

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
