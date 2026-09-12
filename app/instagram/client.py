"""Compliant, multi-layer Instagram media resolver.

Resolution Hierarchy:
1. Offline Mock Mode (for automated testing and sandbox environments)
2. Native yt-dlp Extractor (industry-standard, zero-token, robust CDN extraction)
3. Official Meta Graph API (when INSTAGRAM_ACCESS_TOKEN is configured)
4. Instagram Web GraphQL Query API (doc_id 10015901848480474 with X-IG-App-ID)
5. Instagram Web Item Info API (?__a=1&__d=dis with X-IG-App-ID)
6. Public Embed Frame & OpenGraph fallback
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from app.config import Config
from app.instagram.models import ContentType, InstagramContent, InstagramMediaItem, MediaType
from app.instagram.parser import ParsedInstagramUrl

logger = logging.getLogger(__name__)

INSTAGRAM_WEB_APP_ID = "936619743392459"
GRAPHQL_DOC_ID = "10015901848480474"


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
                    "X-IG-App-ID": INSTAGRAM_WEB_APP_ID,
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

        # 1. Offline Mock Mode
        if self.config.instagram_auth_method == "mock":
            return self._resolve_mock(parsed_url)

        # 2. Native yt-dlp Extractor (Zero-Token, robust CDN extraction)
        try:
            return await self._resolve_via_ytdlp(parsed_url)
        except ImportError:
            logger.debug("yt-dlp is not installed, proceeding to API fallback methods")
        except Exception as e:
            logger.warning("yt-dlp extractor error (%s), attempting API fallback", e)

        # 3. Official Meta Graph API (if access token provided)
        if self.config.instagram_access_token:
            try:
                return await self._resolve_via_graph_api(parsed_url)
            except Exception as e:
                logger.warning(
                    "Meta Graph API resolution failed (%s), falling back to public resolver", e
                )

        # 4. Instagram Web GraphQL Query
        try:
            return await self._resolve_via_graphql(parsed_url)
        except Exception as e:
            logger.debug("GraphQL query failed (%s), trying item info endpoint", e)

        # 5. Instagram Web Item Info API (?__a=1&__d=dis)
        try:
            return await self._resolve_via_item_info(parsed_url)
        except Exception as e:
            logger.debug("Item info endpoint failed (%s), trying embed frame", e)

        # 6. Public Embed Frame Fallback
        return await self._resolve_via_public_embed(parsed_url)

    async def _resolve_via_ytdlp(self, parsed_url: ParsedInstagramUrl) -> InstagramContent:
        """Extracts media directly using yt-dlp without requiring any Meta Developer tokens."""
        import yt_dlp  # Raises ImportError if not installed

        loop = asyncio.get_running_loop()

        def _extract():
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "extract_flat": False,
                "http_headers": {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Accept-Language": "en-US,en;q=0.9",
                },
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(parsed_url.canonical_url, download=False)

        info = await loop.run_in_executor(None, _extract)
        if not info:
            raise InstagramAPIError("yt-dlp returned empty info object")

        shortcode = parsed_url.content_id
        username = info.get("uploader") or info.get("uploader_id") or ""
        caption = info.get("description") or info.get("title") or ""

        # Check for multi-item carousel
        entries = info.get("entries")
        items: List[InstagramMediaItem] = []

        if entries:
            for idx, entry in enumerate(entries):
                if not entry:
                    continue
                url = entry.get("url")
                if not url:
                    continue
                ext = entry.get("ext", "").lower()
                is_vid = entry.get("vcodec") not in (None, "none") or ext in ("mp4", "m4v", "mov", "webm")
                items.append(
                    InstagramMediaItem(
                        url=url,
                        media_type=MediaType.VIDEO if is_vid else MediaType.PHOTO,
                        content_id=shortcode,
                        item_id=f"{shortcode}_{idx}",
                        mime_type="video/mp4" if is_vid else "image/jpeg",
                    )
                )
            content_type = ContentType.CAROUSEL
        else:
            url = info.get("url")
            if not url:
                formats = info.get("formats", [])
                if formats:
                    url = formats[-1].get("url")

            if not url:
                raise InstagramAPIError("No media stream URL extracted by yt-dlp")

            ext = info.get("ext", "").lower()
            is_vid = (
                info.get("vcodec") not in (None, "none")
                or ext in ("mp4", "m4v", "mov", "webm")
                or parsed_url.content_type == ContentType.REEL
            )

            items.append(
                InstagramMediaItem(
                    url=url,
                    media_type=MediaType.VIDEO if is_vid else MediaType.PHOTO,
                    content_id=shortcode,
                    item_id=f"{shortcode}_main",
                    mime_type="video/mp4" if is_vid else "image/jpeg",
                )
            )
            content_type = ContentType.REEL if is_vid else ContentType.POST

        return InstagramContent(
            content_id=shortcode,
            original_url=parsed_url.raw_url,
            canonical_url=parsed_url.canonical_url,
            content_type=content_type,
            username=username,
            caption=caption,
            items=items,
            is_authenticated=False,
        )

    def _resolve_mock(self, parsed_url: ParsedInstagramUrl) -> InstagramContent:
        content_id = parsed_url.content_id
        if "deleted" in content_id.lower() or "404" in content_id:
            raise InstagramContentNotFoundError("This post has been deleted or is unavailable.")
        if "private" in content_id.lower():
            raise InstagramPermissionDeniedError("This content is from a private account.")
        if "expired" in content_id.lower():
            raise InstagramContentExpiredError("This Instagram story has expired.")

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
            username="reels_creator",
            caption="Mock Reel video downloaded successfully.",
            items=items,
            is_authenticated=True,
        )

    async def _resolve_via_graph_api(self, parsed_url: ParsedInstagramUrl) -> InstagramContent:
        client = await self._get_client()
        oembed_url = f"{self.GRAPH_API_BASE}/instagram_oembed"
        params: Dict[str, str] = {
            "url": parsed_url.canonical_url,
            "omitscript": "true",
            "access_token": self.config.instagram_access_token,
        }

        response = await client.get(oembed_url, params=params)
        if response.status_code != 200:
            raise InstagramAPIError(f"Meta Graph API error status: {response.status_code}")

        data = response.json()
        thumbnail_url = data.get("thumbnail_url", "")
        if not thumbnail_url:
            raise InstagramAPIError("No media stream or thumbnail URL returned by Meta API.")

        media_type = (
            MediaType.VIDEO
            if parsed_url.content_type == ContentType.REEL or "video" in data.get("title", "").lower()
            else MediaType.PHOTO
        )

        item = InstagramMediaItem(
            url=thumbnail_url,
            media_type=media_type,
            content_id=parsed_url.content_id,
            item_id=f"{parsed_url.content_id}_0",
        )

        return InstagramContent(
            content_id=parsed_url.content_id,
            original_url=parsed_url.raw_url,
            canonical_url=parsed_url.canonical_url,
            content_type=parsed_url.content_type,
            username=data.get("author_name", ""),
            caption=data.get("title", ""),
            items=[item],
            is_authenticated=True,
        )

    async def _resolve_via_graphql(self, parsed_url: ParsedInstagramUrl) -> InstagramContent:
        client = await self._get_client()
        shortcode = parsed_url.content_id
        api_url = "https://www.instagram.com/api/v1/graphql/query"

        payload = {
            "doc_id": GRAPHQL_DOC_ID,
            "variables": json.dumps({"shortcode": shortcode}),
        }

        resp = await client.post(
            api_url,
            data=payload,
            headers={
                "X-IG-App-ID": INSTAGRAM_WEB_APP_ID,
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": parsed_url.canonical_url,
            },
        )

        if resp.status_code != 200:
            raise InstagramAPIError(f"GraphQL returned HTTP status {resp.status_code}")

        data = resp.json()
        media_data = data.get("data", {}).get("xdt_shortcode_media")
        if not media_data:
            raise InstagramAPIError("No media found in GraphQL response")

        username = media_data.get("owner", {}).get("username", "")
        caption = ""
        caption_edges = media_data.get("edge_media_to_caption", {}).get("edges", [])
        if caption_edges:
            caption = caption_edges[0].get("node", {}).get("text", "")

        carousel_edges = media_data.get("edge_sidecar_to_children", {}).get("edges", [])
        items: List[InstagramMediaItem] = []

        if carousel_edges:
            for idx, edge in enumerate(carousel_edges):
                node = edge.get("node", {})
                is_vid = node.get("is_video", False)
                url = node.get("video_url") if is_vid else node.get("display_url")
                if url:
                    items.append(
                        InstagramMediaItem(
                            url=url,
                            media_type=MediaType.VIDEO if is_vid else MediaType.PHOTO,
                            content_id=shortcode,
                            item_id=f"{shortcode}_{idx}",
                            mime_type="video/mp4" if is_vid else "image/jpeg",
                        )
                    )
            content_type = ContentType.CAROUSEL
        else:
            is_vid = media_data.get("is_video", False)
            url = media_data.get("video_url") if is_vid else media_data.get("display_url")
            if not url:
                raise InstagramAPIError("No media stream URL found in GraphQL media object")
            items.append(
                InstagramMediaItem(
                    url=url,
                    media_type=MediaType.VIDEO if is_vid else MediaType.PHOTO,
                    content_id=shortcode,
                    item_id=f"{shortcode}_main",
                    mime_type="video/mp4" if is_vid else "image/jpeg",
                )
            )
            content_type = ContentType.REEL if is_vid else ContentType.POST

        return InstagramContent(
            content_id=shortcode,
            original_url=parsed_url.raw_url,
            canonical_url=parsed_url.canonical_url,
            content_type=content_type,
            username=username,
            caption=caption,
            items=items,
            is_authenticated=False,
        )

    async def _resolve_via_item_info(self, parsed_url: ParsedInstagramUrl) -> InstagramContent:
        client = await self._get_client()
        shortcode = parsed_url.content_id
        url = f"https://www.instagram.com/p/{shortcode}/?__a=1&__d=dis"

        resp = await client.get(
            url,
            headers={
                "X-IG-App-ID": INSTAGRAM_WEB_APP_ID,
                "Referer": parsed_url.canonical_url,
            },
        )

        if resp.status_code != 200:
            raise InstagramAPIError(f"Item info API returned HTTP {resp.status_code}")

        data = resp.json()
        items_list = data.get("items", [])
        if not items_list:
            raise InstagramAPIError("No items array in response")

        item_data = items_list[0]
        username = item_data.get("user", {}).get("username", "")
        caption = item_data.get("caption", {}).get("text", "") if item_data.get("caption") else ""

        carousel_media = item_data.get("carousel_media", [])
        items: List[InstagramMediaItem] = []

        if carousel_media:
            for idx, c_item in enumerate(carousel_media):
                vid_versions = c_item.get("video_versions", [])
                if vid_versions:
                    items.append(
                        InstagramMediaItem(
                            url=vid_versions[0].get("url"),
                            media_type=MediaType.VIDEO,
                            content_id=shortcode,
                            item_id=f"{shortcode}_{idx}",
                            mime_type="video/mp4",
                        )
                    )
                else:
                    img_candidates = c_item.get("image_versions2", {}).get("candidates", [])
                    if img_candidates:
                        items.append(
                            InstagramMediaItem(
                                url=img_candidates[0].get("url"),
                                media_type=MediaType.PHOTO,
                                content_id=shortcode,
                                item_id=f"{shortcode}_{idx}",
                                mime_type="image/jpeg",
                            )
                        )
            content_type = ContentType.CAROUSEL
        else:
            vid_versions = item_data.get("video_versions", [])
            if vid_versions:
                items.append(
                    InstagramMediaItem(
                        url=vid_versions[0].get("url"),
                        media_type=MediaType.VIDEO,
                        content_id=shortcode,
                        item_id=f"{shortcode}_main",
                        mime_type="video/mp4",
                    )
                )
                content_type = ContentType.REEL
            else:
                img_candidates = item_data.get("image_versions2", {}).get("candidates", [])
                if img_candidates:
                    items.append(
                        InstagramMediaItem(
                            url=img_candidates[0].get("url"),
                            media_type=MediaType.PHOTO,
                            content_id=shortcode,
                            item_id=f"{shortcode}_main",
                            mime_type="image/jpeg",
                        )
                    )
                    content_type = ContentType.POST
                else:
                    raise InstagramAPIError("No media versions in item data")

        return InstagramContent(
            content_id=shortcode,
            original_url=parsed_url.raw_url,
            canonical_url=parsed_url.canonical_url,
            content_type=content_type,
            username=username,
            caption=caption,
            items=items,
            is_authenticated=False,
        )

    async def _resolve_via_public_embed(self, parsed_url: ParsedInstagramUrl) -> InstagramContent:
        client = await self._get_client()
        shortcode = parsed_url.content_id
        embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"

        resp = await client.get(
            embed_url,
            headers={"Referer": "https://www.instagram.com/"},
        )
        if resp.status_code == 404:
            raise InstagramContentNotFoundError("This post has been deleted or does not exist.")

        html_text = resp.text
        video_url = None
        video_match = re.search(r'<video[^>]+src=[\"\']([^\"\']+)[\"\']', html_text)
        if video_match:
            video_url = html.unescape(video_match.group(1))

        if not video_url:
            json_video = re.search(r'\"video_url\":[\"\']([^\"\']+)[\"\']', html_text)
            if json_video:
                video_url = json_video.group(1).encode("utf-8").decode("unicode_escape")

        image_url = None
        img_match = re.search(
            r'<img[^>]+class=[\"\'][^\"\']*EmbeddedMediaImage[^\"\']*[\"\'][^>]+src=[\"\']([^\"\']+)[\"\']',
            html_text,
        )
        if img_match:
            image_url = html.unescape(img_match.group(1))

        if not image_url:
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

        if not video_url and not image_url:
            raise InstagramPermissionDeniedError(
                "Cannot resolve media stream for this post. "
                "The post may be from a private account, age-restricted, or requires login."
            )

        items = []
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
        else:
            items.append(
                InstagramMediaItem(
                    url=image_url,
                    media_type=MediaType.PHOTO,
                    content_id=shortcode,
                    item_id=f"{shortcode}_photo",
                    mime_type="image/jpeg",
                )
            )

        return InstagramContent(
            content_id=shortcode,
            original_url=parsed_url.raw_url,
            canonical_url=parsed_url.canonical_url,
            content_type=ContentType.REEL if video_url else ContentType.POST,
            username="instagram_user",
            caption="",
            items=items,
            is_authenticated=False,
        )
