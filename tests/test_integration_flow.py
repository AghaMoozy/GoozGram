"""Comprehensive end-to-end integration and bot simulation tests."""

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.bot.bot import TelegramBot
from app.bot.handlers.commands import CommandHandlers
from app.bot.handlers.messages import MessageHandlers
from app.bot.middlewares.auth import AuthorizationMiddleware
from app.config import Config
from app.database.models import MediaStatus
from app.database.repository import MediaRepository
from app.instagram.client import InstagramClient
from app.instagram.downloader import MediaDownloader
from app.instagram.models import ContentType, InstagramContent, InstagramMediaItem, MediaType
from app.services.media_service import MediaService
from app.telegram.client import TelegramClient, TelegramRateLimitError
from app.telegram.sender import TelegramMediaSender


class TestIntegrationFlow(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.download_dir = Path(self.temp_dir.name) / "downloads"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(self.temp_dir.name) / "data" / "bot.db"

        self.cfg = Config(
            telegram_bot_token="test_mock_token_12345",
            authorized_telegram_user_ids={1001, 1002},
            download_dir=self.download_dir,
            keep_downloads=False,
            instagram_auth_method="mock",
        )

        self.repo = MediaRepository(self.db_path)
        await self.repo.init_db()

        self.mock_tg_client = MagicMock(spec=TelegramClient)
        self.mock_tg_client.get_me = AsyncMock(return_value={"id": 999, "username": "test_bot"})
        self.mock_tg_client.send_message = AsyncMock(return_value={"ok": True, "message_id": 10})
        self.mock_tg_client.delete_message = AsyncMock(return_value=True)
        self.mock_tg_client.send_photo = AsyncMock(return_value={"ok": True, "message_id": 11})
        self.mock_tg_client.send_video = AsyncMock(return_value={"ok": True, "message_id": 12})
        self.mock_tg_client.send_media_group = AsyncMock(return_value=[{"ok": True, "message_id": 13}])

        self.ig_client = InstagramClient(self.cfg)
        self.downloader = MediaDownloader(self.cfg)
        self.sender = TelegramMediaSender(self.cfg, self.mock_tg_client)

        self.media_service = MediaService(
            config=self.cfg,
            repository=self.repo,
            instagram_client=self.ig_client,
            downloader=self.downloader,
            sender=self.sender,
            telegram_client=self.mock_tg_client,
        )

        self.commands = CommandHandlers(self.cfg, self.mock_tg_client, self.repo)
        self.messages = MessageHandlers(self.mock_tg_client, self.media_service, self.commands)
        self.auth = AuthorizationMiddleware(self.cfg)
        self.bot = TelegramBot(self.cfg, self.mock_tg_client, self.auth, self.commands, self.messages)

    async def asyncTearDown(self):
        await self.ig_client.close()
        await self.downloader.close()
        self.temp_dir.cleanup()

    async def test_unauthorized_user_blocked(self):
        """Ensures non-whitelisted users are immediately rejected."""
        update = {
            "update_id": 1,
            "message": {
                "message_id": 50,
                "chat": {"id": 9999},
                "from": {"id": 9999, "first_name": "Stranger"},
                "text": "https://www.instagram.com/p/C123abc/",
            },
        }
        await self.bot._dispatch_update(update)

        self.mock_tg_client.send_message.assert_awaited_once()
        call_args = self.mock_tg_client.send_message.call_args; sent_text = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("text", "")
        self.assertIn("Access Denied", sent_text)

        # Database should have no record created
        record = await self.repo.get_by_content_id("C123abc")
        self.assertIsNone(record)

    async def test_authorized_user_command_flow(self):
        """Simulates an authorized user sending /start and /status."""
        start_update = {
            "update_id": 2,
            "message": {
                "message_id": 51,
                "chat": {"id": 1001},
                "from": {"id": 1001, "first_name": "Alireza"},
                "text": "/start",
            },
        }
        await self.bot._dispatch_update(start_update)
        call_args = self.mock_tg_client.send_message.call_args; sent_text = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("text", "")
        self.assertIn("Welcome to your Personal Instagram Downloader", sent_text)

        status_update = {
            "update_id": 3,
            "message": {
                "message_id": 52,
                "chat": {"id": 1001},
                "from": {"id": 1001, "first_name": "Alireza"},
                "text": "/status",
            },
        }
        await self.bot._dispatch_update(status_update)
        call_args = self.mock_tg_client.send_message.call_args; status_text = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("text", "")
        self.assertIn("Bot Status & Statistics", status_text)

    async def test_carousel_split_over_ten_items(self):
        """Verifies that an album with > 10 items splits into multiple sendMediaGroup calls."""
        items = []
        for i in range(12):
            p = self.download_dir / f"carousel_{i}.jpg"
            p.write_bytes(b"\xff\xd8\xff" + b"\x00" * 20)
            items.append(
                InstagramMediaItem(
                    url=f"https://example.com/c_{i}.jpg",
                    media_type=MediaType.PHOTO,
                    content_id="carousel_12",
                    item_id=str(i),
                    file_path=p,
                    file_size_bytes=23,
                )
            )

        content = InstagramContent(
            content_id="carousel_12",
            original_url="https://www.instagram.com/p/carousel_12/",
            canonical_url="https://www.instagram.com/p/carousel_12/",
            content_type=ContentType.CAROUSEL,
            items=items,
        )

        await self.sender.send_media(chat_id=1001, content=content, downloaded_items=items)

        # Should be called twice (10 items in first call, 2 items in second call)
        self.assertEqual(self.mock_tg_client.send_media_group.await_count, 2)

    async def test_rate_limit_error_handling(self):
        """Verifies that TelegramRateLimitError carries retry_after properly."""
        err = TelegramRateLimitError("Too Many Requests", retry_after=5)
        self.assertEqual(err.retry_after, 5)
        self.assertIn("Too Many Requests", str(err))


if __name__ == "__main__":
    unittest.main()
