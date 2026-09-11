"""Compliant, authorized Instagram API client.

Distinguishes between public content, authenticated account content, and
inaccessible private/expired content. Adheres strictly to Meta platform policies
and avoids credential scraping, cookie theft, or anti-bot circumvention.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from app.config import Config
from app.instagram.models import ContentType, InstagramContent, InstagramMediaItem, MediaType
from app.instagram.parser import ParsedInstagramUrl

logger = logging.getLogger(__name__)


class InstagramError(Exception):
    """Base exception for Instagram operations."""


class InstagramAuthenticationError(InstagramError):
    """Raised when access token is invalid, expired, or missing."""


class InstagramPermissionDeniedError(InstagramError):
    """Raised when content belongs to a private account or requires higher permissions."""


class InstagramContentNotFoundError(InstagramError):
    """Raised when post, reel, or media was deleted or cannot be found."""


class InstagramContentExpiredError(InstagramError):
    """Raised when a story has expired (past 24h window)."""


class InstagramRateLimitError(InstagramError):
    """Raised when Meta API rate limits are encountered."""


class InstagramAPIError(InstagramError):
    """Raised for general upstream Meta API errors."""


class InstagramClient:
    """Client for resolving Instagram media via compliant official APIs."""

    GRAPH_API_BASE = "https://graph.facebook.com/v19.0"

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

    async def resolve_content(self, parsed_url: ParsedInstagramUrl) -> InstagramContent:
        """Resolves Instagram content metadata and download URLs according to configured auth method."""
        logger.info("Resolving Instagram media for %s (%s)", parsed_url.canonical_url, parsed_url.content_type.value)

        # Simulation / Offline Mock Mode for tests or local execution without live Meta credentials
        if self.config.instagram_auth_method == "mock":
            return self._resolve_mock(parsed_url)

        # Meta Graph API / oEmbed
        if not self.config.instagram_access_token:
            logger.warning("No INSTAGRAM_ACCESS_TOKEN provided. Public resolution may be restricted.")

        return await self._resolve_via_graph_api(parsed_url)

    def _resolve_mock(self, parsed_url: ParsedInstagramUrl) -> InstagramContent:
        """Returns mock content for testing and sandbox environments."""
        content_id = parsed_url.content_id

        if "deleted" in content_id.lower() or "404" in content_id:
            raise InstagramContentNotFoundError("This post has been deleted or is unavailable.")
        if "private" in content_id.lower():
            raise InstagramPermissionDeniedError(
                "This content is from a private account and cannot be accessed without authorization."
            )
        if "expired" in content_id.lower():
            raise InstagramContentExpiredError("This Instagram story has expired (>24 hours).")

        # Carousel mock
        if "carousel" in content_id.lower():
            items = [
                InstagramMediaItem(
                    url="https://images.unsplash.com/photo-1579546929518-9e396f3cc809?w=800",
                    media_type=MediaType.PHOTO,
                    content_id=content_id,
                    item_id=f"{content_id}_1",
                    mime_type="image/jpeg",
                ),
                InstagramMediaItem(
                    url="https://images.unsplash.com/photo-1557683316-973673baf926?w=800",
                    media_type=MediaType.PHOTO,
                    content_id=content_id,
                    item_id=f"{content_id}_2",
                    mime_type="image/jpeg",
                ),
            ]
            return InstagramContent(
                content_id=content_id,
                original_url=parsed_url.raw_url,
                canonical_url=parsed_url.canonical_url,
                content_type=ContentType.CAROUSEL,
                username=self.config.instagram_account or "demo_user",
                caption="Mock Carousel post downloaded successfully.",
                items=items,
                is_authenticated=True,
            )

        # Video / Reel mock
        if parsed_url.content_type == ContentType.REEL or "video" in content_id.lower():
            items = [
                InstagramMediaItem(
                    url="https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
                    media_type=MediaType.VIDEO,
                    content_id=content_id,
                    item_id=f"{content_id}_video",
                    mime_type="video/mp4",
                )
            ]
            return InstagramContent(
                content_id=content_id,
                original_url=parsed_url.raw_url,
                canonical_url=parsed_url.canonical_url,
                content_type=ContentType.REEL,
                username=self.config.instagram_account or "reels_creator",
                caption="Mock Reel video downloaded successfully.",
                items=items,
                is_authenticated=True,
            )

        # Standard Photo Post mock
        items = [
            InstagramMediaItem(
                url="https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=800",
                media_type=MediaType.PHOTO,
                content_id=content_id,
                item_id=f"{content_id}_photo",
                mime_type="image/jpeg",
            )
        ]
        return InstagramContent(
            content_id=content_id,
            original_url=parsed_url.raw_url,
            canonical_url=parsed_url.canonical_url,
            content_type=ContentType.POST,
            username=self.config.instagram_account or "instagram_user",
            caption="Mock Single Image post downloaded successfully.",
            items=items,
            is_authenticated=True,
        )

    async def _resolve_via_graph_api(self, parsed_url: ParsedInstagramUrl) -> InstagramContent:
        """Resolves media via official Meta Graph API endpoints (oEmbed or Graph Node)."""
        client = await self._get_client()

        # oEmbed endpoint provides metadata and official media thumbnail for public URLs
        oembed_url = f"{self.GRAPH_API_BASE}/instagram_oembed"
        params: Dict[str, str] = {
            "url": parsed_url.canonical_url,
            "omitscript": "true",
        }
        if self.config.instagram_access_token:
            params["access_token"] = self.config.instagram_access_token

        try:
            response = await client.get(oembed_url, params=params)
        except httpx.RequestError as e:
            logger.error("Network error contacting Meta API: %s", e)
            raise InstagramAPIError(f"Network error communicating with Instagram API: {e}") from e

        if response.status_code == 401:
            raise InstagramAuthenticationError("Meta Graph API access token is invalid or expired.")
        if response.status_code == 403:
            raise InstagramPermissionDeniedError(
                "Access denied by Instagram. The account may be private or permissions are missing."
            )
        if response.status_code == 404:
            raise InstagramContentNotFoundError("The requested Instagram content was not found or was deleted.")
        if response.status_code == 429:
            raise InstagramRateLimitError("Meta API rate limit exceeded. Please wait before retrying.")

        if response.status_code != 200:
            error_msg = f"Instagram API returned status {response.status_code}: {response.text}"
            logger.error(error_msg)
            raise InstagramAPIError(error_msg)

        data = response.json()
        author_name = data.get("author_name", "")
        title = data.get("title", "")
        thumbnail_url = data.get("thumbnail_url", "")

        if not thumbnail_url:
            raise InstagramAPIError("No media stream or thumbnail URL returned by Meta API.")

        # Determine media type from oEmbed hints or parsed URL
        media_type = (
            MediaType.VIDEO
            if parsed_url.content_type == ContentType.REEL or "video" in title.lower()
            else MediaType.PHOTO
        )

        item = InstagramMediaItem(
            url=thumbnail_url,
            media_type=media_type,
            content_id=parsed_url.content_id,
            item_id=f"{parsed_url.content_id}_0",
            width=data.get("thumbnail_width"),
            height=data.get("thumbnail_height"),
        )

        return InstagramContent(
            content_id=parsed_url.content_id,
            original_url=parsed_url.raw_url,
            canonical_url=parsed_url.canonical_url,
            content_type=parsed_url.content_type,
            username=author_name,
            caption=title,
            items=[item],
            is_authenticated=bool(self.config.instagram_access_token),
        )
