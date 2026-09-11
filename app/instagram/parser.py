"""Instagram URL parsing, validation, and content identifier extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse

from app.instagram.models import ContentType


class InstagramParserError(Exception):
    """Base error for Instagram parsing failures."""


class InvalidInstagramURLError(InstagramParserError):
    """Raised when a URL is malformed or not from Instagram."""


class UnsupportedInstagramURLError(InstagramParserError):
    """Raised when an Instagram URL format is recognized but not supported for media extraction."""


@dataclass
class ParsedInstagramUrl:
    raw_url: str
    canonical_url: str
    content_type: ContentType
    content_id: str
    username: Optional[str] = None


# Matches links within message text
INSTAGRAM_URL_FINDER_REGEX = re.compile(
    r"https?://(?:www\.)?(?:instagram\.com|instagr\.am)/[a-zA-Z0-9_\-./?=&%]+",
    re.IGNORECASE,
)

# Supported patterns
POST_REGEX = re.compile(
    r"^/(?:p|tv)/([a-zA-Z0-9_\-]+)",
    re.IGNORECASE,
)

REEL_REGEX = re.compile(
    r"^/(?:reel|reels)/([a-zA-Z0-9_\-]+)",
    re.IGNORECASE,
)

STORY_REGEX = re.compile(
    r"^/stories/([a-zA-Z0-9_.]+)/([0-9]+)",
    re.IGNORECASE,
)

SHARE_REGEX = re.compile(
    r"^/share/(?:p|reel)/([a-zA-Z0-9_\-]+)",
    re.IGNORECASE,
)


def extract_instagram_urls(text: str) -> List[str]:
    """Finds all potential Instagram URLs in an arbitrary text string."""
    if not text:
        return []
    return INSTAGRAM_URL_FINDER_REGEX.findall(text)


def parse_instagram_url(url_str: str) -> ParsedInstagramUrl:
    """Parses and validates an Instagram URL.

    Raises:
        InvalidInstagramURLError: If the URL is not valid or not an Instagram URL.
        UnsupportedInstagramURLError: If the URL is a profile, tag, explore, or other unsupported page.
    """
    if not url_str or not isinstance(url_str, str):
        raise InvalidInstagramURLError("Empty or non-string URL provided")

    cleaned_url = url_str.strip()
    if not cleaned_url.startswith(("http://", "https://")):
        cleaned_url = "https://" + cleaned_url

    try:
        parsed = urlparse(cleaned_url)
    except Exception as e:
        raise InvalidInstagramURLError(f"Malformed URL structure: {e}") from e

    hostname = (parsed.hostname or "").lower()
    if hostname not in ("instagram.com", "www.instagram.com", "instagr.am"):
        raise InvalidInstagramURLError(f"Domain '{hostname}' is not a valid Instagram domain")

    path = parsed.path.rstrip("/")
    if not path:
        raise UnsupportedInstagramURLError("Root Instagram URL does not refer to specific media")

    # Match Post
    post_match = POST_REGEX.match(path)
    if post_match:
        shortcode = post_match.group(1)
        canonical = f"https://www.instagram.com/p/{shortcode}/"
        return ParsedInstagramUrl(
            raw_url=url_str,
            canonical_url=canonical,
            content_type=ContentType.POST,
            content_id=shortcode,
        )

    # Match Reel
    reel_match = REEL_REGEX.match(path)
    if reel_match:
        shortcode = reel_match.group(1)
        canonical = f"https://www.instagram.com/reel/{shortcode}/"
        return ParsedInstagramUrl(
            raw_url=url_str,
            canonical_url=canonical,
            content_type=ContentType.REEL,
            content_id=shortcode,
        )

    # Match Story
    story_match = STORY_REGEX.match(path)
    if story_match:
        username = story_match.group(1)
        story_id = story_match.group(2)
        canonical = f"https://www.instagram.com/stories/{username}/{story_id}/"
        return ParsedInstagramUrl(
            raw_url=url_str,
            canonical_url=canonical,
            content_type=ContentType.STORY,
            content_id=f"{username}_{story_id}",
            username=username,
        )

    # Match Share links
    share_match = SHARE_REGEX.match(path)
    if share_match:
        shortcode = share_match.group(1)
        canonical = f"https://www.instagram.com/p/{shortcode}/"
        return ParsedInstagramUrl(
            raw_url=url_str,
            canonical_url=canonical,
            content_type=ContentType.POST,
            content_id=shortcode,
        )

    # Check for recognized unsupported paths
    if path.startswith(("/explore", "/direct", "/accounts", "/reels", "/stories")):
        raise UnsupportedInstagramURLError(
            f"Instagram path '{path}' does not point to downloadable media"
        )

    # Single segment username profile (e.g. /username)
    segments = [s for s in path.split("/") if s]
    if len(segments) == 1:
        raise UnsupportedInstagramURLError(
            f"Profile URL for '@{segments[0]}' does not point to specific media"
        )

    raise UnsupportedInstagramURLError(f"Unsupported Instagram URL pattern: {path}")
