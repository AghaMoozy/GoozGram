"""Unit tests for Telegram caption formatting, media routing, and size guards."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from app.config import Config
from app.instagram.models import ContentType, InstagramContent, InstagramMediaItem, MediaType
from app.telegram.client import TelegramClient
from app.telegram.sender import TelegramFileSizeError, TelegramMediaSender


class TestTelegramSender(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.cfg = Config(
            telegram_bot_token="1234:TOKEN",
            authorized_telegram_user_ids={12345},
        )
        self.mock_client = MagicMock(spec=TelegramClient)
        self.mock_client.send_photo = AsyncMock(return_value={"ok": True, "message_id": 101})
        self.mock_client.send_video = AsyncMock(return_value={"ok": True, "message_id": 102})
        self.mock_client.send_media_group = AsyncMock(return_value=[{"ok": True, "message_id": 103}])
        self.mock_client.send_message = AsyncMock(return_value={"ok": True, "message_id": 104})
        self.sender = TelegramMediaSender(self.cfg, self.mock_client)
        self.temp_dir = tempfile.TemporaryDirectory()

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    def test_caption_formatting(self):
        content = InstagramContent(
            content_id="C123abc",
            original_url="https://www.instagram.com/p/C123abc/",
            canonical_url="https://www.instagram.com/p/C123abc/",
            content_type=ContentType.POST,
            username="test_photographer",
            caption="Sunset at the beach!",
        )
        caption = self.sender.format_caption(content)
        self.assertIn("@test_photographer", caption)
        self.assertIn("https://www.instagram.com/p/C123abc/", caption)
        self.assertIn("Sunset at the beach!", caption)

    async def test_send_single_photo(self):
        photo_path = Path(self.temp_dir.name) / "test.jpg"
        photo_path.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)

        content = InstagramContent(
            content_id="photo1",
            original_url="https://www.instagram.com/p/photo1/",
            canonical_url="https://www.instagram.com/p/photo1/",
            content_type=ContentType.POST,
            username="user1",
        )
        item = InstagramMediaItem(
            url="https://example.com/p.jpg",
            media_type=MediaType.PHOTO,
            content_id="photo1",
            file_path=photo_path,
            file_size_bytes=103,
        )

        res = await self.sender.send_media(chat_id=12345, content=content, downloaded_items=[item])
        self.mock_client.send_photo.assert_awaited_once()
        self.assertEqual(res.get("message_id"), 101)

    async def test_send_single_video(self):
        video_path = Path(self.temp_dir.name) / "test.mp4"
        video_path.write_bytes(b"\x00\x00\x00\x18ftyp" + b"\x00" * 100)

        content = InstagramContent(
            content_id="reel1",
            original_url="https://www.instagram.com/reel/reel1/",
            canonical_url="https://www.instagram.com/reel/reel1/",
            content_type=ContentType.REEL,
            username="user2",
        )
        item = InstagramMediaItem(
            url="https://example.com/v.mp4",
            media_type=MediaType.VIDEO,
            content_id="reel1",
            file_path=video_path,
            file_size_bytes=104,
        )

        res = await self.sender.send_media(chat_id=12345, content=content, downloaded_items=[item])
        self.mock_client.send_video.assert_awaited_once()
        self.assertEqual(res.get("message_id"), 102)

    async def test_oversized_file_limit_guard(self):
        oversized_path = Path(self.temp_dir.name) / "huge.mp4"
        oversized_path.write_bytes(b"0" * 100)

        content = InstagramContent(
            content_id="huge",
            original_url="https://www.instagram.com/reel/huge/",
            canonical_url="https://www.instagram.com/reel/huge/",
            content_type=ContentType.REEL,
        )
        item = InstagramMediaItem(
            url="https://example.com/huge.mp4",
            media_type=MediaType.VIDEO,
            content_id="huge",
            file_path=oversized_path,
            file_size_bytes=60 * 1024 * 1024,  # 60MB > 50MB limit
        )

        with self.assertRaises(TelegramFileSizeError):
            await self.sender.send_media(chat_id=12345, content=content, downloaded_items=[item])
        self.mock_client.send_message.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
