import json
import unittest

from app.services.llm_output_validator import _parse_validation_result, build_validation_payload
from app.services.sql_mistake_store import _mistake_fingerprint
from app.services.sql_safety_validator import validate_sql_safety


SCHEMA = {
    "tables": [
        {
            "name": "attendances",
            "columns": [
                {"name": "id", "type": "bigint"},
                {"name": "employee_id", "type": "bigint"},
                {"name": "date", "type": "date"},
            ],
        },
        {
            "name": "users",
            "columns": [
                {"name": "id", "type": "bigint"},
                {"name": "name", "type": "varchar"},
            ],
        },
    ],
    "relationships": [{"from": "attendances.employee_id", "to": "users.id"}],
}


class JudgeValidationTests(unittest.TestCase):
    def test_backend_reports_missing_column_as_structured_root_cause(self) -> None:
        result = validate_sql_safety(
            "SELECT a.attendance_status FROM attendances a LIMIT 10",
            SCHEMA,
        )

        self.assertFalse(result.isValid)
        self.assertEqual(result.mistakeType, "invalid_column")
        self.assertEqual(result.table, "attendances")
        self.assertEqual(result.column, "attendance_status")

    def test_judge_payload_contains_business_and_deterministic_context(self) -> None:
        payload = build_validation_payload(
            question="Show less present employees",
            schema=SCHEMA,
            generated_sql="SELECT a.employee_id FROM attendances a LIMIT 10",
            report_category="attendance",
            start_date="2025-01-01",
            end_date="2026-12-31",
            current_user_role="HR",
            deterministic_validation={"isValid": True},
        )

        self.assertEqual(payload["report_category"], "attendance")
        self.assertEqual(payload["requested_date_range"]["end_date"], "2026-12-31")
        self.assertEqual(payload["current_user_role"], "HR")
        self.assertTrue(payload["deterministic_validation"]["isValid"])

    def test_judge_structured_rejection_parses(self) -> None:
        result = _parse_validation_result(
            json.dumps(
                {
                    "is_valid": False,
                    "reason": "The query counts all attendance rows as present.",
                    "error_type": "wrong_aggregation",
                    "validation_stage": "judge",
                    "fix_hint": "Use the real presence indicator in the attendance schema.",
                    "retryable": True,
                    "missing_table": None,
                    "missing_column": None,
                }
            )
        )

        self.assertFalse(result.is_valid)
        self.assertEqual(result.error_type, "wrong_aggregation")
        self.assertTrue(result.retryable)

    def test_mistake_fingerprint_deduplicates_whitespace_variants(self) -> None:
        first = _mistake_fingerprint(
            "attempt-1",
            "SELECT  a.bad_column\nFROM attendances a",
            "Column does not exist.",
            "schema",
            "backend",
        )
        second = _mistake_fingerprint(
            "attempt-1",
            " select a.bad_column from attendances a ",
            " column does not exist. ",
            "schema",
            "backend",
        )

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
