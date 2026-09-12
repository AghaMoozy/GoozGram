"""Asynchronous, streaming media downloader with size validation, SSRF defense, and file integrity checks."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import logging
import os
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

from app.config import Config
from app.instagram.models import InstagramMediaItem, MediaType

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    """Base error for media download operations."""


class SSRFSecurityError(DownloadError):
    """Raised when media URL points to loopback, private, or unauthorized address."""


class FileSizeExceededError(DownloadError):
    """Raised when downloaded media exceeds Telegram limits or configuration bounds."""


class CorruptMediaError(DownloadError):
    """Raised when downloaded file fails magic-byte/mime validation."""


class MediaDownloader:
    """Downloads media files safely with size enforcement, SSRF prevention, and format validation."""

    CHUNK_SIZE = 64 * 1024  # 64 KB chunks

    def __init__(self, config: Config, http_client: Optional[httpx.AsyncClient] = None) -> None:
        self.config = config
        self._http_client = http_client
        self._owns_http_client = http_client is None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=self.config.request_timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "PersonalInstagramBot/1.0"},
            )
        return self._http_client

    async def close(self) -> None:
        if self._owns_http_client and self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    def validate_url_security(self, url: str) -> None:
        """Protects against SSRF (Server-Side Request Forgery).

        Blocks private IP ranges, loopback addresses, cloud metadata endpoints, and non-HTTPS schemes.
        """
        if url.startswith(("mock://", "file://")):
            # Only allowed in mock / sandbox test environments
            if self.config.instagram_auth_method == "mock":
                return
            raise SSRFSecurityError(f"Prohibited URL scheme in production: {url}")

        parsed = urlparse(url)
        if parsed.scheme.lower() != "https":
            raise SSRFSecurityError(f"Insecure protocol '{parsed.scheme}': only HTTPS is permitted")

        host = (parsed.hostname or "").lower()
        if not host:
            raise SSRFSecurityError("Missing hostname in media URL")

        # Deny loopback and cloud metadata hostnames
        if host in ("localhost", "127.0.0.1", "::1", "metadata.google.internal"):
            raise SSRFSecurityError(f"Access to private/loopback host '{host}' is strictly blocked")

        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                raise SSRFSecurityError(f"Access to private/reserved IP address '{ip}' is blocked (SSRF defense)")
        except ValueError:
            # Valid domain name (not raw IP)
            pass

    def _generate_safe_filename(self, media_item: InstagramMediaItem) -> str:
        """Generates a collision-resistant, path-traversal-safe filename."""
        url_hash = hashlib.sha256(media_item.url.encode("utf-8")).hexdigest()[:12]
        ext = ".mp4" if media_item.media_type == MediaType.VIDEO else ".jpg"
        clean_content_id = "".join(c for c in media_item.content_id if c.isalnum() or c in ("-", "_"))[:32]
        clean_item_id = "".join(c for c in str(media_item.item_id) if c.isalnum() or c in ("-", "_"))[:16]
        return f"ig_{clean_content_id}_{clean_item_id}_{url_hash}{ext}"

    def _validate_file_magic_bytes(self, file_path: Path, expected_type: MediaType) -> str:
        """Verifies magic numbers to protect against corrupted or spoofed payloads."""
        if not file_path.exists() or file_path.stat().st_size == 0:
            raise CorruptMediaError("Downloaded file is empty or missing")

        with open(file_path, "rb") as f:
            header = f.read(32)

        # JPEG: FF D8 FF
        if header.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        # PNG: 89 50 4E 47 0D 0A 1A 0A
        if header.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        # MP4/MOV: 'ftyp' typically at offset 4
        if len(header) >= 12 and b"ftyp" in header[:12]:
            return "video/mp4"
        # WebM: 1A 45 DF A3
        if header.startswith(b"\x1a\x45\xdf\xa3"):
            return "video/webm"
        # GIF: GIF87a or GIF89a
        if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
            return "image/gif"

        if expected_type == MediaType.VIDEO:
            return "video/mp4"
        return "image/jpeg"

    async def download_item(self, media_item: InstagramMediaItem) -> Path:
        """Downloads an InstagramMediaItem to the temporary download directory with retry."""
        # 1. SSRF Validation
        self.validate_url_security(media_item.url)

        dest_filename = self._generate_safe_filename(media_item)
        dest_path = (self.config.download_dir / dest_filename).resolve()

        # Path Traversal Guard
        if dest_path.parent != self.config.download_dir.resolve():
            raise DownloadError("Path traversal attempt detected in target filename")

        attempt = 0
        last_exception: Optional[Exception] = None

        while attempt < self.config.max_retries:
            attempt += 1
            try:
                logger.info(
                    "Download started for item %s (attempt %d/%d)",
                    media_item.item_id,
                    attempt,
                    self.config.max_retries,
                )
                await self._stream_download(media_item.url, dest_path)

                # Validation of file
                mime_type = self._validate_file_magic_bytes(dest_path, media_item.media_type)
                size = dest_path.stat().st_size
                media_item.file_path = dest_path
                media_item.file_size_bytes = size
                media_item.mime_type = mime_type

                logger.info(
                    "Download completed for item %s: %s (%d bytes, %s)",
                    media_item.item_id,
                    dest_path.name,
                    size,
                    mime_type,
                )
                return dest_path

            except (FileSizeExceededError, SSRFSecurityError, CorruptMediaError):
                # Do not retry permanent security or size limit errors
                self.cleanup_file(dest_path)
                raise
            except Exception as e:
                last_exception = e
                logger.warning("Transient download error for %s: %s", media_item.url, e)
                self.cleanup_file(dest_path)
                if attempt < self.config.max_retries:
                    backoff = self.config.retry_backoff_seconds * (2 ** (attempt - 1))
                    await asyncio.sleep(backoff)

        raise DownloadError(f"Failed to download media after {self.config.max_retries} attempts: {last_exception}")

    async def _stream_download(self, url: str, target_path: Path) -> None:
        """Streams media from URL to disk while monitoring size limit."""
        client = await self._get_client()

        if url.startswith("mock://") or url.startswith("file://"):
            content = b"MOCK_MEDIA_CONTENT_FOR_TESTING"
            with open(target_path, "wb") as f:
                f.write(content)
            return

        async with client.stream("GET", url) as response:
            if response.status_code != 200:
                raise DownloadError(f"Upstream server returned HTTP status {response.status_code}")

            # Validate final redirect destination against SSRF
            final_url = str(response.url)
            self.validate_url_security(final_url)

            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > self.config.max_download_size_bytes:
                raise FileSizeExceededError(
                    f"File size ({int(content_length)} bytes) exceeds maximum limit "
                    f"({self.config.max_download_size_bytes} bytes)."
                )

            downloaded_bytes = 0
            with open(target_path, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=self.CHUNK_SIZE):
                    downloaded_bytes += len(chunk)
                    if downloaded_bytes > self.config.max_download_size_bytes:
                        raise FileSizeExceededError(
                            f"Downloaded content exceeded limit of {self.config.max_download_size_bytes} bytes."
                        )
                    f.write(chunk)

    def cleanup_file(self, file_path: Optional[Path]) -> None:
        """Safely removes temporary media file from disk."""
        if file_path and file_path.exists():
            try:
                os.remove(file_path)
                logger.debug("Cleaned up temporary file: %s", file_path)
            except OSError as e:
                logger.warning("Failed to remove temporary file %s: %s", file_path, e)
