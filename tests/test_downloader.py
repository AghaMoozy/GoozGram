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


class TestSSRFDefense(unittest.TestCase):

    def setUp(self):
        self.cfg = Config(telegram_bot_token="test", instagram_auth_method="graph_api")
        self.downloader = MediaDownloader(self.cfg)

    def test_ssrf_blocked_hosts(self):
        from app.instagram.downloader import SSRFSecurityError
        blocked_urls = [
            "http://127.0.0.1:8000/webhook",
            "http://localhost:8000/",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.1/admin",
            "http://192.168.1.1/secret",
            "http://172.16.0.1/internal",
            "file:///etc/passwd",
            "gopher://localhost:70/",
        ]
        for url in blocked_urls:
            with self.assertRaises(SSRFSecurityError, msg=f"Failed to block SSRF URL: {url}"):
                self.downloader.validate_url_security(url)

    def test_ssrf_allowed_valid_https(self):
        valid_urls = [
            "https://instagram.fsan1-1.fna.fbcdn.net/v/t51.2885-15/pic.jpg",
            "https://scontent.cdninstagram.com/v/t51.2885-15/video.mp4",
            "https://images.unsplash.com/photo-1507525428034",
        ]
        for url in valid_urls:
            try:
                self.downloader.validate_url_security(url)
            except Exception as e:
                self.fail(f"Valid HTTPS URL unexpectedly raised error: {url} -> {e}")
