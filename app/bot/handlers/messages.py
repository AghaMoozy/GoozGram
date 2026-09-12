"""Telegram Bot message handlers with bilingual Persian & English routing."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional, Set

from app.bot.handlers.commands import CommandHandlers
from app.database.repository import MediaRepository
from app.i18n import t
from app.instagram.parser import extract_instagram_urls
from app.services.media_service import MediaService
from app.telegram.client import TelegramClient

logger = logging.getLogger(__name__)


class MessageHandlers:
    """Handles text messages and user input routing with localization."""

    def __init__(
        self,
        telegram_client: TelegramClient,
        media_service: MediaService,
        command_handlers: CommandHandlers,
        repository: Optional[MediaRepository] = None,
    ) -> None:
        self.client = telegram_client
        self.media_service = media_service
        self.commands = command_handlers
        self.repository = repository
        self._background_tasks: Set[asyncio.Task[Any]] = set()

    async def handle_message(self, message: Dict[str, Any]) -> None:
        chat_id = message.get("chat", {}).get("id")
        user = message.get("from", {})
        user_id = user.get("id")
        first_name = user.get("first_name", "")
        text = (message.get("text") or "").strip()

        if not chat_id or not text:
            return

        uid = user_id or chat_id

        # 1. Handle command clicks in Persian and English
        if text in ("/start", "Start", "شروع"):
            await self.commands.handle_start(chat_id, user_id=uid, user_name=first_name)
            return
        if text in ("/help", "ℹ️ Help", "Help", "ℹ️ راهنما", "راهنما"):
            await self.commands.handle_help(chat_id, user_id=uid)
            return
        if text in ("/status", "📊 Status", "Status", "📊 وضعیت", "وضعیت"):
            await self.commands.handle_status(chat_id, user_id=uid)
            return
        if text in ("/settings", "⚙️ Settings", "Settings", "⚙️ تنظیمات", "تنظیمات"):
            await self.commands.handle_settings(chat_id, user_id=uid)
            return
        if text in ("/cancel", "❌ Cancel", "Cancel", "❌ لغو", "لغو"):
            await self.commands.handle_cancel(chat_id, user_id=uid)
            return

        # 2. Extract Instagram URLs
        urls = extract_instagram_urls(text)

        if not urls:
            lang = (await self.repository.get_user_language(uid)) if self.repository else "fa"
            await self.client.send_message(
                chat_id=chat_id,
                text=t("no_link_detected", lang or "fa"),
            )
            return

        # 3. Process each detected URL asynchronously
        for url in urls:
            logger.info("Spawning async processing task for URL: %s in chat %s", url, chat_id)
            task = asyncio.create_task(self.media_service.process_url(url, chat_id, user_id=uid))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
