"""Compliant, multi-layer Instagram media resolver.

Supports:
1. Official Meta Graph API (when INSTAGRAM_ACCESS_TOKEN is configured)
2. Public Instagram embed & OpenGraph stream resolution (for public posts/reels without token)
3. Mock mode for offline testing and verification
"""

from __future__ import annotations

import html
import json
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import unquote

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
    """Client for resolving Instagram media via compliant official and public APIs."""

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
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
        return self._http_client

    async def close(self) -> None:
        if self._owns_http_client and self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def resolve_content(self, parsed_url: ParsedInstagramUrl) -> InstagramContent:
        """Resolves Instagram content metadata and download URLs."""
        logger.info(
            "Resolving Instagram media for %s (%s)",
            parsed_url.canonical_url,
            parsed_url.content_type.value,
        )

        # 1. Simulation / Offline Mock Mode
        if self.config.instagram_auth_method == "mock":
            return self._resolve_mock(parsed_url)

        # 2. If Meta Access Token is configured, attempt official Graph API first
        if self.config.instagram_access_token:
            try:
                return await self._resolve_via_graph_api(parsed_url)
            except Exception as e:
                logger.warning(
                    "Meta Graph API resolution failed (%s), falling back to public resolver", e
                )

        # 3. Public Web Embed & OpenGraph resolver (Fallback for public posts/reels without token)
        return await self._resolve_via_public_embed(parsed_url)

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
        """Resolves media via official Meta Graph API endpoints."""
        client = await self._get_client()

        oembed_url = f"{self.GRAPH_API_BASE}/instagram_oembed"
        params: Dict[str, str] = {
            "url": parsed_url.canonical_url,
            "omitscript": "true",
            "access_token": self.config.instagram_access_token,
        }

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
            raise InstagramAPIError(f"Instagram API returned status {response.status_code}: {response.text}")

        data = response.json()
        author_name = data.get("author_name", "")
        title = data.get("title", "")
        thumbnail_url = data.get("thumbnail_url", "")

        if not thumbnail_url:
            raise InstagramAPIError("No media stream or thumbnail URL returned by Meta API.")

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
            is_authenticated=True,
        )

    async def _resolve_via_public_embed(self, parsed_url: ParsedInstagramUrl) -> InstagramContent:
        """Resolves public posts and reels via Instagram's official public embed interface."""
        client = await self._get_client()
        shortcode = parsed_url.content_id
        embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"

        logger.info("Fetching public embed frame for %s", embed_url)
        try:
            resp = await client.get(
                embed_url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Referer": "https://www.instagram.com/",
                },
            )
        except Exception as e:
            logger.error("Failed to fetch public embed frame: %s", e)
            raise InstagramAPIError(f"Failed to connect to Instagram embed service: {e}") from e

        if resp.status_code == 404:
            raise InstagramContentNotFoundError(
                "This post has been deleted or does not exist."
            )

        html_text = resp.text

        # 1. Check for video stream in embed HTML
        # Look for video src in <video> tag or embedded JS JSON
        video_url: Optional[str] = None
        video_match = re.search(r'<video[^>]+src=[\"\']([^\"\']+)[\"\']', html_text)
        if video_match:
            video_url = html.unescape(video_match.group(1))

        if not video_url:
            # Check JSON patterns inside <script>
            json_video = re.search(r'\"video_url\":[\"\']([^\"\']+)[\"\']', html_text)
            if json_video:
                video_url = json_video.group(1).encode("utf-8").decode("unicode_escape")

        # 2. Check for image stream
        image_url: Optional[str] = None
        img_match = re.search(
            r'<img[^>]+class=[\"\'][^\"\']*EmbeddedMediaImage[^\"\']*[\"\'][^>]+src=[\"\']([^\"\']+)[\"\']',
            html_text,
        )
        if img_match:
            image_url = html.unescape(img_match.group(1))

        if not image_url:
            # Fallback to og:image meta tag
            og_img = re.search(
                r'<meta[^>]+property=[\"\']og:image[\"\'][^>]+content=[\"\']([^\"\']+)[\"\']',
                html_text,
            )
            if not og_img:
                og_img = re.search(
                    r'<meta[^>]+content=[\"\']([^\"\']+)[\"\'][^>]+property=[\"\']og:image[\"\']',
                    html_text,
                )
            if og_img:
                image_url = html.unescape(og_img.group(1))

        if not image_url:
            json_img = re.search(r'\"display_url\":[\"\']([^\"\']+)[\"\']', html_text)
            if json_img:
                image_url = json_img.group(1).encode("utf-8").decode("unicode_escape")

        # 3. Check author and caption
        author_name = ""
        author_match = re.search(
            r'class=[\"\'][^\"\']*CaptionUsername[^\"\']*[\"\'][^>]*>([^<]+)<',
            html_text,
        )
        if author_match:
            author_name = author_match.group(1).strip()
        else:
            og_title = re.search(
                r'<meta[^>]+property=[\"\']og:title[\"\'][^>]+content=[\"\']([^\"\']+)[\"\']',
                html_text,
            )
            if og_title:
                title_val = html.unescape(og_title.group(1))
                if "•" in title_val:
                    author_name = title_val.split("•")[0].replace("Instagram post by", "").strip()

        caption_text = ""
        caption_match = re.search(
            r'class=[\"\'][^\"\']*CaptionText[^\"\']*[\"\'][^>]*>(.*?)</div>',
            html_text,
            re.DOTALL,
        )
        if caption_match:
            # Strip tags
            raw_caption = re.sub(r'<[^>]+>', '', caption_match.group(1))
            caption_text = html.unescape(raw_caption).strip()

        # Decide final media type and stream
        items: List[InstagramMediaItem] = []
        if video_url:
            items.append(
                InstagramMediaItem(
                    url=video_url,
                    media_type=MediaType.VIDEO,
                    content_id=shortcode,
                    item_id=f"{shortcode}_video",
                    mime_type="video/mp4",
                )
            )
        elif image_url:
            items.append(
                InstagramMediaItem(
                    url=image_url,
                    media_type=MediaType.PHOTO,
                    content_id=shortcode,
                    item_id=f"{shortcode}_photo",
                    mime_type="image/jpeg",
                )
            )
        else:
            # If neither video nor image was found, check if it's restricted/private
            raise InstagramPermissionDeniedError(
                "Cannot resolve media stream for this post. "
                "The post may be from a private account, age-restricted, or requires login."
            )

        content_type = (
            ContentType.REEL
            if parsed_url.content_type == ContentType.REEL or video_url
            else ContentType.POST
        )

        return InstagramContent(
            content_id=shortcode,
            original_url=parsed_url.raw_url,
            canonical_url=parsed_url.canonical_url,
            content_type=content_type,
            username=author_name or (parsed_url.username or "instagram_user"),
            caption=caption_text,
            items=items,
            is_authenticated=False,
        )
