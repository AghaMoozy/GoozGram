"""Instagram data models representing parsed content and downloadable media."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional


class ContentType(str, Enum):
    POST = "POST"
    REEL = "REEL"
    STORY = "STORY"
    CAROUSEL = "CAROUSEL"
    UNKNOWN = "UNKNOWN"


class MediaType(str, Enum):
    PHOTO = "photo"
    VIDEO = "video"
    UNKNOWN = "unknown"


@dataclass
class InstagramMediaItem:
    """Represents an individual downloadable photo or video item."""
    url: str
    media_type: MediaType
    content_id: str
    item_id: str = ""
    width: Optional[int] = None
    height: Optional[int] = None
    file_path: Optional[Path] = None
    file_size_bytes: int = 0
    mime_type: str = ""


@dataclass
class InstagramContent:
    """Represents a resolved Instagram post, reel, story, or carousel."""
    content_id: str
    original_url: str
    canonical_url: str
    content_type: ContentType
    username: str = ""
    caption: str = ""
    items: List[InstagramMediaItem] = field(default_factory=list)
    is_authenticated: bool = False
    is_private: bool = False
    is_expired: bool = False
    created_at: Optional[str] = None

    @property
    def is_carousel(self) -> bool:
        return len(self.items) > 1 or self.content_type == ContentType.CAROUSEL

    @property
    def primary_media_type(self) -> MediaType:
        if not self.items:
            return MediaType.UNKNOWN
        if len(self.items) == 1:
            return self.items[0].media_type
        return MediaType.PHOTO if any(i.media_type == MediaType.PHOTO for i in self.items) else MediaType.VIDEO
