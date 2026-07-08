import unittest
from datetime import date

from app.services.catalog import load_schema_catalog, resolve_report_category
from app.services.date_resolver import resolve_date_range
from app.services.llm import build_sql_generation_payload_preview
from app.services.sql_safety_validator import validate_sql_safety
from app.services.templates import find_template


class DailyReportTemplateTests(unittest.TestCase):
    def test_daily_report_matches_reference_blueprint(self) -> None:
        template = find_template("Daily Report", "task")

        self.assertIsNotNone(template)
        self.assertEqual(template.title, "Daily Report")
        self.assertEqual(template.blueprint["layout"], "daily_progress_matrix")
        self.assertIn("CAD_CAM Projects", template.blueprint["sections"])
        self.assertIn("BIM Projects", template.blueprint["sections"])
        self.assertIn("E-Drawing Projects", template.blueprint["sections"])
        self.assertIn("assign_team_leader", template.blueprint["schema_hints"]["team_leader_source"])
        self.assertIn("daily_created_tasks", template.sql)
        self.assertIn("daily_completed_tasks", template.sql)
        self.assertIn("weekly_created_tasks", template.sql)
        self.assertIn("p.project_type_id IS NOT NULL", template.sql)
        self.assertNotEqual(template.sql.strip(), "SELECT p.project_name, COUNT(pt.id) AS task_count")

        safety = validate_sql_safety(template.sql, load_schema_catalog(), require_limit=False)
        self.assertTrue(safety.isValid, safety.reason)

    def test_daily_report_category_detection_uses_task_guidance(self) -> None:
        category = resolve_report_category(None, "Daily Report")

        self.assertIsNotNone(category)
        self.assertEqual(category["id"], "task")
        self.assertIn("Daily Report", category["templates"])

    def test_daily_report_without_date_defaults_to_today(self) -> None:
        today = date.today().isoformat()

        resolved = resolve_date_range("Daily Report", None, None, "task")

        self.assertEqual(resolved.start_date, today)
        self.assertEqual(resolved.end_date, today)
        self.assertTrue(any("today" in item for item in resolved.assumptions))

    def test_daily_report_reference_payload_keeps_business_shape(self) -> None:
        template = find_template("Daily report for BIM projects by team leader", "task")
        self.assertIsNotNone(template)

        payload = build_sql_generation_payload_preview(
            "Daily report for BIM projects by team leader",
            "2026-07-08",
            "2026-07-08",
            report_category={"id": "task", "label": "Task Report", "strict_mode": False},
            reference_report={
                "title": template.title,
                "sql": template.sql,
                "explanation": template.explanation,
                "blueprint": template.blueprint,
            },
        )

        self.assertEqual(payload["reference_report"]["title"], "Daily Report")
        self.assertEqual(payload["reference_report"]["blueprint"]["layout"], "daily_progress_matrix")
        self.assertTrue(
            any("Do not reduce a Daily Report to only project_name and task_count" in item for item in payload["requirements_preview"])
        )


if __name__ == "__main__":
    unittest.main()
