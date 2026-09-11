"""Unit tests for media downloading, magic byte detection, and size limits."""

import tempfile
import unittest
from pathlib import Path

from app.config import Config
from app.instagram.downloader import (
    CorruptMediaError,
    FileSizeExceededError,
    MediaDownloader,
)
from app.instagram.models import InstagramMediaItem, MediaType


class TestDownloader(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.download_dir = Path(self.temp_dir.name)
        self.cfg = Config(
            telegram_bot_token="test_token",
            download_dir=self.download_dir,
            max_download_size_bytes=1024 * 1024,  # 1 MB for testing
        )
        self.downloader = MediaDownloader(self.cfg)

    async def asyncTearDown(self):
        await self.downloader.close()
        self.temp_dir.cleanup()

    def test_magic_byte_validation(self):
        # Valid JPEG header
        jpeg_file = self.download_dir / "test.jpg"
        with open(jpeg_file, "wb") as f:
            f.write(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 50)
        mime = self.downloader._validate_file_magic_bytes(jpeg_file, MediaType.PHOTO)
        self.assertEqual(mime, "image/jpeg")

        # Valid PNG header
        png_file = self.download_dir / "test.png"
        with open(png_file, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
        mime = self.downloader._validate_file_magic_bytes(png_file, MediaType.PHOTO)
        self.assertEqual(mime, "image/png")

        # Valid MP4 header
        mp4_file = self.download_dir / "test.mp4"
        with open(mp4_file, "wb") as f:
            f.write(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 50)
        mime = self.downloader._validate_file_magic_bytes(mp4_file, MediaType.VIDEO)
        self.assertEqual(mime, "video/mp4")

        # Corrupt / Empty file
        empty_file = self.download_dir / "empty.bin"
        empty_file.touch()
        with self.assertRaises(CorruptMediaError):
            self.downloader._validate_file_magic_bytes(empty_file, MediaType.PHOTO)

    def test_cleanup_file(self):
        temp_file = self.download_dir / "temp_to_delete.tmp"
        temp_file.write_text("temporary content")
        self.assertTrue(temp_file.exists())
        self.downloader.cleanup_file(temp_file)
        self.assertFalse(temp_file.exists())

    def test_safe_filename(self):
        item = InstagramMediaItem(
            url="https://example.com/media/file.jpg",
            media_type=MediaType.PHOTO,
            content_id="test../../id",
            item_id="0",
        )
        safe_name = self.downloader._generate_safe_filename(item)
        self.assertNotIn("..", safe_name)
        self.assertTrue(safe_name.startswith("ig_testid_0_"))
        self.assertTrue(safe_name.endswith(".jpg"))


if __name__ == "__main__":
    unittest.main()
