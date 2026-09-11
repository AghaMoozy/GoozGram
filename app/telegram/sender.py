"""Telegram media delivery handler with size limit enforcement and format routing."""

from __future__ import annotations

import html
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import Config
from app.instagram.models import InstagramContent, InstagramMediaItem, MediaType
from app.telegram.client import TelegramAPIError, TelegramClient

logger = logging.getLogger(__name__)


class TelegramDeliveryError(Exception):
    """Raised when Telegram delivery encounters an error."""


class TelegramFileSizeError(TelegramDeliveryError):
    """Raised when media exceeds Telegram's 50MB bot upload limit."""


class TelegramMediaSender:
    """Handles sending downloaded Instagram media to Telegram users."""

    MAX_TELEGRAM_BOT_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
    MAX_ALBUM_SIZE = 10  # Telegram allows max 10 items per sendMediaGroup

    def __init__(self, config: Config, client: TelegramClient) -> None:
        self.config = config
        self.client = client

    def format_caption(self, content: InstagramContent, max_length: int = 1024) -> str:
        """Formats clean, informative caption with source and metadata."""
        lines = ["<b>Instagram media downloaded successfully</b>\n"]

        if content.username:
            lines.append(f"<b>Source:</b>\n@{html.escape(content.username)}\n")

        if content.canonical_url:
            lines.append(f"<b>URL:</b>\n{html.escape(content.canonical_url)}\n")

        if content.caption:
            clean_caption = content.caption.strip()
            # Truncate caption if necessary to fit Telegram's 1024 char caption limit
            remaining = max_length - len("".join(lines)) - 25
            if len(clean_caption) > remaining:
                clean_caption = clean_caption[:max(remaining, 50)] + "..."
            lines.append(f"<b>Caption:</b>\n{html.escape(clean_caption)}")

        return "\n".join(lines).strip()

    async def send_media(
        self,
        chat_id: int | str,
        content: InstagramContent,
        downloaded_items: List[InstagramMediaItem],
    ) -> Dict[str, Any]:
        """Routes media delivery to sendPhoto, sendVideo, or sendMediaGroup."""
        if not downloaded_items:
            raise TelegramDeliveryError("No downloaded media items available to send")

        # 1. Enforce Telegram file size limits
        for item in downloaded_items:
            if not item.file_path or not item.file_path.exists():
                raise TelegramDeliveryError(f"Media file not found on disk: {item.item_id}")
            size = item.file_size_bytes or item.file_path.stat().st_size
            if size > self.MAX_TELEGRAM_BOT_FILE_SIZE:
                err_msg = (
                    f"⚠️ <b>File Size Limit Exceeded</b>\n\n"
                    f"The requested media file ({size / (1024 * 1024):.1f} MB) exceeds Telegram's "
                    f"bot upload limit of 50 MB.\n\n"
                    f"<b>Direct link:</b> {content.canonical_url}"
                )
                await self.client.send_message(chat_id, err_msg)
                raise TelegramFileSizeError(f"File {item.file_path.name} exceeds 50MB Telegram limit")

        caption = self.format_caption(content)
        logger.info("Delivering %d media item(s) to Telegram chat %s", len(downloaded_items), chat_id)

        # 2. Single item delivery
        if len(downloaded_items) == 1:
            item = downloaded_items[0]
            if item.media_type == MediaType.VIDEO:
                return await self.client.send_video(
                    chat_id=chat_id,
                    video_path=item.file_path,
                    caption=caption,
                )
            else:
                return await self.client.send_photo(
                    chat_id=chat_id,
                    photo_path=item.file_path,
                    caption=caption,
                )

        # 3. Carousel / Multi-item delivery (sendMediaGroup)
        # Split into chunks of 10 if necessary
        chunks = [
            downloaded_items[i : i + self.MAX_ALBUM_SIZE]
            for i in range(0, len(downloaded_items), self.MAX_ALBUM_SIZE)
        ]

        last_result: Dict[str, Any] = {}
        for chunk_idx, chunk in enumerate(chunks):
            media_group: List[Dict[str, Any]] = []
            file_map: Dict[str, Path] = {}

            for idx, item in enumerate(chunk):
                attach_id = f"attach_{idx}"
                file_map[attach_id] = item.file_path
                mtype = "video" if item.media_type == MediaType.VIDEO else "photo"

                media_entry: Dict[str, Any] = {
                    "type": mtype,
                    "media": f"attach://{attach_id}",
                }
                # Caption only on the first item of the first album
                if chunk_idx == 0 and idx == 0:
                    media_entry["caption"] = caption
                    media_entry["parse_mode"] = "HTML"

                media_group.append(media_entry)

            res = await self.client.send_media_group(
                chat_id=chat_id,
                media_group=media_group,
                file_map=file_map,
            )
            last_result = res[0] if isinstance(res, list) and res else {}

        return last_result
