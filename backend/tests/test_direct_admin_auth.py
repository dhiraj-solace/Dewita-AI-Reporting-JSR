import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services import users


def _settings(**overrides):
    values = {
        "direct_admin_enabled": True,
        "direct_admin_email": "admin@example.com",
        "direct_admin_password": "TemporaryPassword123!",
        "auth_secret_key": "test-auth-secret",
        "auth_token_ttl_minutes": 60,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _unexpected_database_access():
    raise AssertionError("database should not be used")


class DirectAdminAuthTests(unittest.TestCase):
    def test_login_and_token_validation_do_not_use_database(self):
        with (
            patch.object(users, "get_settings", side_effect=lambda: _settings()),
            patch.object(users, "get_engine", side_effect=_unexpected_database_access),
        ):
            user = users.authenticate_user(
                "ADMIN@example.com",
                "TemporaryPassword123!",
            )

            self.assertIsNotNone(user)
            self.assertEqual(user["id"], users.DIRECT_ADMIN_ID)
            self.assertEqual(user["role_name"], "Super Admin")
            token = users.create_auth_token(user)
            self.assertEqual(users.get_user_from_token(token), user)

    def test_wrong_password_does_not_fall_back_to_database(self):
        with (
            patch.object(users, "get_settings", side_effect=lambda: _settings()),
            patch.object(users, "get_engine", side_effect=_unexpected_database_access),
        ):
            user = users.authenticate_user("admin@example.com", "WrongPassword")

        self.assertIsNone(user)

    def test_direct_admin_is_disabled_without_complete_credentials(self):
        with patch.object(
            users,
            "get_settings",
            side_effect=lambda: _settings(direct_admin_password=None),
        ):
            self.assertIsNone(users._configured_direct_admin())


if __name__ == "__main__":
    unittest.main()
