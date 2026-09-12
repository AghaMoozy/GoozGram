"""Database models and status definitions for media tracking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class MediaStatus(str, Enum):
    PENDING = "PENDING"
    DOWNLOADING = "DOWNLOADING"
    DOWNLOADED = "DOWNLOADED"
    SENT = "SENT"
    FAILED = "FAILED"


class DeliveryStatus(str, Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class MediaRecord:
    id: Optional[int]
    content_id: str
    url: str
    media_type: str
    status: MediaStatus
    telegram_chat_id: Optional[int] = None
    telegram_message_id: Optional[int] = None
    delivery_status: DeliveryStatus = DeliveryStatus.PENDING
    error_message: Optional[str] = None
    retry_count: int = 0
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        now_iso = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now_iso
        if not self.updated_at:
            self.updated_at = now_iso
        if isinstance(self.status, str):
            self.status = MediaStatus(self.status)
        if isinstance(self.delivery_status, str):
            self.delivery_status = DeliveryStatus(self.delivery_status)
