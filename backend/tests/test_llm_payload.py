import unittest

from app.services.llm import build_sql_generation_payload_preview
from app.services.templates import find_template


class LlmPayloadTests(unittest.TestCase):
    def test_timesheet_payload_filters_poisoned_mistake_examples(self) -> None:
        template = find_template("Vinit Thakare timesheet report", "timesheet")
        self.assertIsNotNone(template)

        payload = build_sql_generation_payload_preview(
            "Vinit Thakare timesheet report",
            None,
            None,
            mistake_examples=[
                {
                    "user_question": "HR Timesheet Report",
                    "wrong_sql": "clarification_needed start_date and end_date are required for the HR Timesheet Report.",
                    "reason": "Only SELECT/CTE report queries are allowed.",
                    "correct_sql": "Regenerate a safe SQL query.",
                },
                {
                    "user_question": "HR Timesheet Report",
                    "wrong_sql": "SELECT tr.role_type FROM timelog_records tr",
                    "reason": "Column `role_type` does not exist on table `timelog_records`.",
                    "correct_sql": "work_type",
                },
            ],
            report_category={
                "id": "timesheet",
                "label": "Timesheet Report",
                "strict_mode": False,
                "preferred_tables": ["timelog_records", "users", "projects"],
                "allowed_tables": ["timelog_records", "users", "projects"],
                "metrics": ["total_hours", "non_billable_hours", "entry_count"],
                "filters": ["date_range", "employee", "project", "work_type", "user_type"],
            },
            reference_report={
                "title": template.title,
                "sql": template.sql,
                "explanation": template.explanation,
            },
        )

        self.assertEqual(payload["reference_report"]["title"], "Team Timesheet Report")
        self.assertIn("YEARWEEK", payload["reference_report"]["sql"])
        self.assertEqual(payload["mistake_examples_count"], 0)
        self.assertTrue(
            any(
                "Never return clarification_needed only because a timesheet date range is missing" in item
                for item in payload["requirements_preview"]
            )
        )


if __name__ == "__main__":
    unittest.main()
