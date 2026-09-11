"""End-to-end media processing pipeline and duplicate prevention orchestrator."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import List, Optional

from app.config import Config
from app.database.models import DeliveryStatus, MediaRecord, MediaStatus
from app.database.repository import MediaRepository
from app.instagram.client import (
    InstagramAuthenticationError,
    InstagramClient,
    InstagramContentExpiredError,
    InstagramContentNotFoundError,
    InstagramError,
    InstagramPermissionDeniedError,
    InstagramRateLimitError,
)
from app.instagram.downloader import (
    CorruptMediaError,
    DownloadError,
    FileSizeExceededError,
    MediaDownloader,
)
from app.instagram.models import InstagramContent, InstagramMediaItem
from app.instagram.parser import (
    InvalidInstagramURLError,
    ParsedInstagramUrl,
    UnsupportedInstagramURLError,
    parse_instagram_url,
)
from app.telegram.client import TelegramClient
from app.telegram.sender import TelegramDeliveryError, TelegramFileSizeError, TelegramMediaSender

logger = logging.getLogger(__name__)


@dataclass
class ProcessResult:
    success: bool
    content_id: str
    message: str
    record: Optional[MediaRecord] = None


class MediaService:
    """Coordinates Instagram media resolution, downloading, database tracking, and Telegram delivery."""

    def __init__(
        self,
        config: Config,
        repository: MediaRepository,
        instagram_client: InstagramClient,
        downloader: MediaDownloader,
        sender: TelegramMediaSender,
        telegram_client: TelegramClient,
    ) -> None:
        self.config = config
        self.repository = repository
        self.instagram_client = instagram_client
        self.downloader = downloader
        self.sender = sender
        self.telegram_client = telegram_client

    async def process_url(
        self,
        raw_url: str,
        chat_id: int,
        force_retry: bool = False,
    ) -> ProcessResult:
        """Executes the complete asynchronous pipeline for a single Instagram URL."""
        logger.info("Instagram request received: %s from chat %s", raw_url, chat_id)

        # 1. URL Validation & Parsing
        try:
            parsed_url = parse_instagram_url(raw_url)
        except InvalidInstagramURLError as e:
            logger.warning("Invalid Instagram URL: %s (%s)", raw_url, e)
            await self._notify_user_error(chat_id, f"❌ <b>Invalid Instagram URL</b>\n\n{e}")
            return ProcessResult(success=False, content_id="", message=str(e))
        except UnsupportedInstagramURLError as e:
            logger.warning("Unsupported Instagram URL: %s (%s)", raw_url, e)
            await self._notify_user_error(
                chat_id,
                f"⚠️ <b>Unsupported Instagram Link</b>\n\n{e}\n\n"
                f"Supported: Posts, Reels, Carousels, and Stories.",
            )
            return ProcessResult(success=False, content_id="", message=str(e))

        content_id = parsed_url.content_id
        record: Optional[MediaRecord] = None
        status_msg_id: Optional[int] = None
        downloaded_items: List[InstagramMediaItem] = []

        try:
            # 2. Duplicate Detection
            existing = await self.repository.get_by_content_id(content_id)
            if existing and not force_retry:
                if existing.status == MediaStatus.SENT:
                    logger.info("Duplicate request for %s already SENT.", content_id)
                    await self.telegram_client.send_message(
                        chat_id,
                        f"ℹ️ <b>Already Processed</b>\n\n"
                        f"This Instagram media (<code>{content_id}</code>) was already downloaded and sent to you.",
                    )
                    return ProcessResult(
                        success=True,
                        content_id=content_id,
                        message="Already sent",
                        record=existing,
                    )
                elif existing.status == MediaStatus.DOWNLOADING:
                    logger.info("Media %s is currently being downloaded.", content_id)
                    await self.telegram_client.send_message(
                        chat_id,
                        f"⏳ <b>In Progress</b>\n\n"
                        f"This media is currently being downloaded. Please wait a moment...",
                    )
                    return ProcessResult(
                        success=False,
                        content_id=content_id,
                        message="In progress",
                        record=existing,
                    )

            # Create or reuse database record
            if existing:
                record = existing
                await self.repository.update_status(record.id, MediaStatus.PENDING)
            else:
                record = await self.repository.create_record(
                    content_id=content_id,
                    url=parsed_url.canonical_url,
                    media_type=parsed_url.content_type.value,
                    telegram_chat_id=chat_id,
                )

            # Inform user of progress
            try:
                status_msg = await self.telegram_client.send_message(
                    chat_id,
                    f"🔍 Resolving media for <code>{content_id}</code>...",
                )
                status_msg_id = status_msg.get("message_id")
            except Exception as e:
                logger.debug("Failed to send preliminary status message: %s", e)

            # 3. Resolve Media
            await self.repository.update_status(record.id, MediaStatus.DOWNLOADING)
            content = await self.instagram_client.resolve_content(parsed_url)
            logger.info(
                "Media resolved: %s with %d item(s)", content.content_id, len(content.items)
            )

            # 4. Download Media Items
            for idx, item in enumerate(content.items, start=1):
                logger.info(
                    "Download started: %s (item %d/%d)",
                    item.content_id,
                    idx,
                    len(content.items),
                )
                file_path = await self.downloader.download_item(item)
                downloaded_items.append(item)
                logger.info("Download completed: %s -> %s", item.content_id, file_path.name)

            await self.repository.update_status(record.id, MediaStatus.DOWNLOADED)

            # 5. Telegram Media Delivery
            logger.info("Telegram delivery started for %s", content_id)
            delivery_res = await self.sender.send_media(
                chat_id=chat_id,
                content=content,
                downloaded_items=downloaded_items,
            )
            logger.info("Telegram delivery completed for %s", content_id)

            msg_id = delivery_res.get("message_id") if isinstance(delivery_res, dict) else None
            await self.repository.update_status(
                record.id,
                MediaStatus.SENT,
                delivery_status=DeliveryStatus.SENT,
                telegram_message_id=msg_id,
            )

            # Clean up preliminary progress message if present
            if status_msg_id is not None:
                await self.telegram_client.delete_message(chat_id, status_msg_id)

            return ProcessResult(
                success=True,
                content_id=content_id,
                message="Successfully downloaded and delivered",
                record=record,
            )

        except (InstagramContentNotFoundError, InstagramContentExpiredError) as e:
            err = f"❌ <b>Content Unavailable</b>\n\n{e}"
            rec_id = record.id if record else None
            await self._handle_failure(rec_id, chat_id, err, str(e))
            return ProcessResult(success=False, content_id=content_id, message=str(e), record=record)

        except (InstagramAuthenticationError, InstagramPermissionDeniedError) as e:
            err = (
                f"🔒 <b>Authentication / Permission Required</b>\n\n"
                f"{e}\n\n"
                f"Private posts or restricted stories require authorized access."
            )
            rec_id = record.id if record else None
            await self._handle_failure(rec_id, chat_id, err, str(e))
            return ProcessResult(success=False, content_id=content_id, message=str(e), record=record)

        except InstagramRateLimitError as e:
            err = f"⏳ <b>Instagram Rate Limit</b>\n\n{e}\nPlease try again in a few minutes."
            rec_id = record.id if record else None
            await self._handle_failure(rec_id, chat_id, err, str(e))
            return ProcessResult(success=False, content_id=content_id, message=str(e), record=record)

        except FileSizeExceededError as e:
            err = f"⚠️ <b>File Size Limit Exceeded</b>\n\n{e}"
            rec_id = record.id if record else None
            await self._handle_failure(rec_id, chat_id, err, str(e))
            return ProcessResult(success=False, content_id=content_id, message=str(e), record=record)

        except (DownloadError, CorruptMediaError) as e:
            err = f"❌ <b>Download Error</b>\n\nFailed to download media stream: {e}"
            rec_id = record.id if record else None
            await self._handle_failure(rec_id, chat_id, err, str(e))
            return ProcessResult(success=False, content_id=content_id, message=str(e), record=record)

        except (TelegramFileSizeError, TelegramDeliveryError) as e:
            err = f"📤 <b>Telegram Delivery Error</b>\n\n{e}"
            rec_id = record.id if record else None
            await self._handle_failure(rec_id, chat_id, err, str(e))
            return ProcessResult(success=False, content_id=content_id, message=str(e), record=record)

        except Exception as e:
            logger.exception("Unexpected error processing %s: %s", content_id, e)
            err = f"⚠️ <b>System Error</b>\n\nAn unexpected error occurred: {e}"
            rec_id = record.id if record else None
            await self._handle_failure(rec_id, chat_id, err, str(e))
            return ProcessResult(success=False, content_id=content_id, message=str(e), record=record)

        finally:
            # 6. Automatic Cleanup
            if not self.config.keep_downloads:
                for item in downloaded_items:
                    self.downloader.cleanup_file(item.file_path)

    async def _handle_failure(
        self, record_id: Optional[int], chat_id: int, user_message: str, error_detail: str
    ) -> None:
        if record_id is not None:
            await self.repository.update_status(
                record_id,
                MediaStatus.FAILED,
                error_message=error_detail,
                delivery_status=DeliveryStatus.FAILED,
            )
            await self.repository.increment_retry(record_id)
        await self._notify_user_error(chat_id, user_message)

    async def _notify_user_error(self, chat_id: int, error_text: str) -> None:
        try:
            await self.telegram_client.send_message(chat_id, error_text)
        except Exception as e:
            logger.error("Failed to send error notification to chat %s: %s", chat_id, e)
