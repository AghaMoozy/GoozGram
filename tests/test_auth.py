"""Unit tests for Telegram user authorization and configuration security."""

import unittest

from app.bot.middlewares.auth import AuthorizationMiddleware
from app.config import Config


class TestAuth(unittest.TestCase):

    def test_authorized_users(self):
        cfg = Config(
            telegram_bot_token="1234:ABCDEF",
            authorized_telegram_user_ids={111222, 333444},
        )
        auth = AuthorizationMiddleware(cfg)
        self.assertTrue(auth.is_authorized(111222))
        self.assertTrue(auth.is_authorized(333444))
        self.assertFalse(auth.is_authorized(999999))
        self.assertFalse(auth.is_authorized(None))

    def test_empty_authorized_users_denies_all(self):
        cfg = Config(
            telegram_bot_token="1234:ABCDEF",
            authorized_telegram_user_ids=set(),
        )
        auth = AuthorizationMiddleware(cfg)
        self.assertFalse(auth.is_authorized(111222))
        self.assertFalse(auth.is_authorized(None))

    def test_secret_masking(self):
        cfg = Config(
            telegram_bot_token="1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ",
            instagram_access_token="EAAB123456789SECRET_TOKEN",
            authorized_telegram_user_ids={12345},
        )
        repr_str = cfg.safe_repr()
        self.assertNotIn("1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ", repr_str)
        self.assertNotIn("EAAB123456789SECRET_TOKEN", repr_str)
        self.assertIn("Config(", repr_str)


if __name__ == "__main__":
    unittest.main()
