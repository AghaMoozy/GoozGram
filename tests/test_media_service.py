"""Unit tests for the end-to-end MediaService pipeline and duplicate handling."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from app.config import Config
from app.database.models import DeliveryStatus, MediaStatus
from app.database.repository import MediaRepository
from app.instagram.client import InstagramClient
from app.instagram.downloader import MediaDownloader
from app.instagram.models import ContentType, InstagramContent, InstagramMediaItem, MediaType
from app.services.media_service import MediaService
from app.telegram.client import TelegramClient
from app.telegram.sender import TelegramMediaSender


class TestMediaService(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.download_dir = Path(self.temp_dir.name) / "downloads"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(self.temp_dir.name) / "data" / "bot.db"

        self.cfg = Config(
            telegram_bot_token="test_token",
            authorized_telegram_user_ids={12345},
            download_dir=self.download_dir,
            keep_downloads=False,
        )

        self.repo = MediaRepository(self.db_path)
        await self.repo.init_db()

        self.mock_ig = MagicMock(spec=InstagramClient)
        self.mock_downloader = MagicMock(spec=MediaDownloader)
        self.mock_sender = MagicMock(spec=TelegramMediaSender)
        self.mock_tg_client = MagicMock(spec=TelegramClient)
        self.mock_tg_client.send_message = AsyncMock(return_value={"ok": True, "message_id": 1})

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

    async def test_successful_pipeline_flow(self):
        sample_file = self.download_dir / "sample.jpg"
        sample_file.write_bytes(b"\xff\xd8\xff" + b"\x00" * 50)

        item = InstagramMediaItem(
            url="https://example.com/pic.jpg",
            media_type=MediaType.PHOTO,
            content_id="postA",
            file_path=sample_file,
            file_size_bytes=53,
        )
        content = InstagramContent(
            content_id="postA",
            original_url="https://www.instagram.com/p/postA/",
            canonical_url="https://www.instagram.com/p/postA/",
            content_type=ContentType.POST,
            items=[item],
        )

        self.mock_ig.resolve_content = AsyncMock(return_value=content)
        self.mock_downloader.download_item = AsyncMock(return_value=sample_file)
        self.mock_sender.send_media = AsyncMock(return_value={"ok": True, "message_id": 99})

        result = await self.service.process_url("https://www.instagram.com/p/postA/", chat_id=12345)
        self.assertTrue(result.success)
        self.assertEqual(result.content_id, "postA")

        # Verify database status is SENT
        record = await self.repo.get_by_content_id("postA")
        self.assertIsNotNone(record)
        self.assertEqual(record.status, MediaStatus.SENT)
        self.assertEqual(record.delivery_status, DeliveryStatus.SENT)

        # Verify cleanup called
        self.mock_downloader.cleanup_file.assert_called_with(sample_file)

    async def test_duplicate_prevention_skips_redownload(self):
        # Pre-seed a SENT record
        record = await self.repo.create_record("post_dup", "https://www.instagram.com/p/post_dup/")
        await self.repo.update_status(record.id, MediaStatus.SENT, delivery_status=DeliveryStatus.SENT)

        result = await self.service.process_url("https://www.instagram.com/p/post_dup/", chat_id=12345)
        self.assertTrue(result.success)
        self.assertEqual(result.message, "Already sent")
        self.mock_ig.resolve_content.assert_not_called()


if __name__ == "__main__":
    unittest.main()


