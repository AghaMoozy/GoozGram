"""Telegram Bot message handlers for incoming links and menu selections."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Set

from app.bot.handlers.commands import CommandHandlers
from app.instagram.parser import extract_instagram_urls
from app.services.media_service import MediaService
from app.telegram.client import TelegramClient

logger = logging.getLogger(__name__)


class MessageHandlers:
    """Handles text messages and user input routing."""

    def __init__(
        self,
        telegram_client: TelegramClient,
        media_service: MediaService,
        command_handlers: CommandHandlers,
    ) -> None:
        self.client = telegram_client
        self.media_service = media_service
        self.commands = command_handlers
        self._background_tasks: Set[asyncio.Task[Any]] = set()

    async def handle_message(self, message: Dict[str, Any]) -> None:
        chat_id = message.get("chat", {}).get("id")
        user = message.get("from", {})
        first_name = user.get("first_name", "")
        text = (message.get("text") or "").strip()

        if not chat_id or not text:
            return

        # Handle button clicks from reply keyboard
        if text in ("/start", "Start"):
            await self.commands.handle_start(chat_id, first_name)
            return
        if text in ("/help", "ℹ️ Help", "Help"):
            await self.commands.handle_help(chat_id)
            return
        if text in ("/status", "📊 Status", "Status"):
            await self.commands.handle_status(chat_id)
            return
        if text in ("/settings", "⚙️ Settings", "Settings"):
            await self.commands.handle_settings(chat_id)
            return
        if text in ("/cancel", "❌ Cancel", "Cancel"):
            await self.commands.handle_cancel(chat_id)
            return

        # Extract Instagram URLs
        urls = extract_instagram_urls(text)

        if not urls:
            # If the user typed an arbitrary text without an Instagram link
            await self.client.send_message(
                chat_id=chat_id,
                text=(
                    "ℹ️ <b>No Instagram link detected</b>\n\n"
                    "Please send a valid Instagram link (Post, Reel, Carousel, or Story), e.g.:\n"
                    "<code>https://www.instagram.com/p/C123abc/</code>\n"
                    "<code>https://www.instagram.com/reel/C456def/</code>"
                ),
            )
            return

        # Process each detected URL asynchronously in the background so updates aren't blocked
        for url in urls:
            logger.info("Spawning async processing task for URL: %s in chat %s", url, chat_id)
            task = asyncio.create_task(self.media_service.process_url(url, chat_id))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
