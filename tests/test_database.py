"""Unit tests for SQLite database repository and duplicate detection."""

import os
import tempfile
import unittest
from pathlib import Path

from app.database.models import DeliveryStatus, MediaStatus
from app.database.repository import MediaRepository


class TestDatabaseRepository(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_bot.db"
        self.repo = MediaRepository(self.db_path)
        await self.repo.init_db()

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    async def test_create_and_get_record(self):
        record = await self.repo.create_record(
            content_id="post_123",
            url="https://www.instagram.com/p/post_123/",
            media_type="photo",
            telegram_chat_id=123456,
        )
        self.assertIsNotNone(record.id)
        self.assertEqual(record.status, MediaStatus.PENDING)
        self.assertEqual(record.delivery_status, DeliveryStatus.PENDING)

        fetched = await self.repo.get_by_content_id("post_123")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.content_id, "post_123")
        self.assertEqual(fetched.telegram_chat_id, 123456)

    async def test_update_status_and_stats(self):
        record = await self.repo.create_record(
            content_id="reel_456",
            url="https://www.instagram.com/reel/reel_456/",
            media_type="video",
            telegram_chat_id=123456,
        )

        await self.repo.update_status(
            record_id=record.id,
            status=MediaStatus.SENT,
            delivery_status=DeliveryStatus.SENT,
            telegram_message_id=999,
        )

        updated = await self.repo.get_by_content_id("reel_456")
        self.assertEqual(updated.status, MediaStatus.SENT)
        self.assertEqual(updated.delivery_status, DeliveryStatus.SENT)
        self.assertEqual(updated.telegram_message_id, 999)

        stats = await self.repo.get_stats()
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["by_status"].get("SENT"), 1)

    async def test_retry_count(self):
        record = await self.repo.create_record(
            content_id="fail_789",
            url="https://www.instagram.com/p/fail_789/",
        )
        count1 = await self.repo.increment_retry(record.id)
        count2 = await self.repo.increment_retry(record.id)
        self.assertEqual(count1, 1)
        self.assertEqual(count2, 2)


if __name__ == "__main__":
    unittest.main()


    async def test_language_persistence(self):
        # Default should be None
        lang = await self.repo.get_user_language(123456)
        self.assertIsNone(lang)

        # Set to Persian
        await self.repo.set_user_language(123456, "fa")
        lang = await self.repo.get_user_language(123456)
        self.assertEqual(lang, "fa")

        # Update to English
        await self.repo.set_user_language(123456, "en")
        lang = await self.repo.get_user_language(123456)
        self.assertEqual(lang, "en")
