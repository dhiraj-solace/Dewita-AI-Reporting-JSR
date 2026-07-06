import unittest

from app.services.query_safety import validate_user_query_safety


class QuerySafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_report_is_allowed_without_intent_classifier(self) -> None:
        result = await validate_user_query_safety(
            "Generate the Week 5 report with totals grouped by project type and manufacturing type."
        )

        self.assertTrue(result.is_safe)
        self.assertEqual(result.intent, "read_report")
        self.assertEqual(result.risk, "low")

    async def test_greeting_only_message_is_blocked(self) -> None:
        result = await validate_user_query_safety("Hello!")

        self.assertFalse(result.is_safe)
        self.assertEqual(result.intent, "non_reporting")

    async def test_greeting_with_report_request_is_allowed(self) -> None:
        result = await validate_user_query_safety("Hello, show the Week 5 project report")

        self.assertTrue(result.is_safe)
        self.assertEqual(result.intent, "read_report")


if __name__ == "__main__":
    unittest.main()
