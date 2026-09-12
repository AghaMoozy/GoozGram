"""Unit tests for resilient error handling (404, 403, expired, rate limits)."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from app.config import Config
from app.database.models import MediaStatus
from app.database.repository import MediaRepository
from app.instagram.client import (
    InstagramClient,
    InstagramContentExpiredError,
    InstagramContentNotFoundError,
    InstagramPermissionDeniedError,
    InstagramRateLimitError,
)
from app.instagram.downloader import DownloadError, MediaDownloader
from app.services.media_service import MediaService
from app.telegram.client import TelegramClient
from app.telegram.sender import TelegramMediaSender


class TestErrorHandling(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cfg = Config(
            telegram_bot_token="test_token",
            authorized_telegram_user_ids={12345},
            download_dir=Path(self.temp_dir.name),
        )
        self.repo = MediaRepository(Path(self.temp_dir.name) / "test.db")
        await self.repo.init_db()

        self.mock_ig = MagicMock(spec=InstagramClient)
        self.mock_downloader = MagicMock(spec=MediaDownloader)
        self.mock_sender = MagicMock(spec=TelegramMediaSender)
        self.mock_tg_client = MagicMock(spec=TelegramClient)
        self.mock_tg_client.send_message = AsyncMock(return_value={"ok": True})

        self.service = MediaService(
            config=self.cfg,
            repository=self.repo,
            instagram_client=self.mock_ig,
            downloader=self.mock_downloader,
            sender=self.mock_sender,
            telegram_client=self.mock_tg_client,
        )

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    async def test_handle_deleted_post(self):
        self.mock_ig.resolve_content = AsyncMock(
            side_effect=InstagramContentNotFoundError("Post has been deleted")
        )
        res = await self.service.process_url("https://www.instagram.com/p/deleted123/", chat_id=12345)
        self.assertFalse(res.success)
        rec = await self.repo.get_by_content_id("deleted123")
        self.assertEqual(rec.status, MediaStatus.FAILED)
        self.mock_tg_client.send_message.assert_awaited()

    async def test_handle_private_account_permission_denied(self):
        self.mock_ig.resolve_content = AsyncMock(
            side_effect=InstagramPermissionDeniedError("Private account requires authorization")
        )
        res = await self.service.process_url("https://www.instagram.com/p/private123/", chat_id=12345)
        self.assertFalse(res.success)
        rec = await self.repo.get_by_content_id("private123")
        self.assertEqual(rec.status, MediaStatus.FAILED)

    async def test_handle_expired_story(self):
        self.mock_ig.resolve_content = AsyncMock(
            side_effect=InstagramContentExpiredError("Story has expired")
        )
        res = await self.service.process_url("https://www.instagram.com/stories/user/123456789/", chat_id=12345)
        self.assertFalse(res.success)
        rec = await self.repo.get_by_content_id("user_123456789")
        self.assertEqual(rec.status, MediaStatus.FAILED)

    async def test_handle_rate_limit(self):
        self.mock_ig.resolve_content = AsyncMock(
            side_effect=InstagramRateLimitError("Rate limit exceeded")
        )
        res = await self.service.process_url("https://www.instagram.com/reel/ratelimit123/", chat_id=12345)
        self.assertFalse(res.success)
        rec = await self.repo.get_by_content_id("ratelimit123")
        self.assertEqual(rec.status, MediaStatus.FAILED)


if __name__ == "__main__":
    unittest.main()
