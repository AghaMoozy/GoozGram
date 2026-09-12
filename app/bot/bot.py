"""Asynchronous Telegram Bot runner and update dispatcher with language callbacks."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from app.bot.handlers.commands import CommandHandlers
from app.bot.handlers.messages import MessageHandlers
from app.bot.keyboards.menu import get_language_inline_keyboard, get_main_reply_keyboard
from app.bot.middlewares.auth import AuthorizationMiddleware
from app.config import Config
from app.database.repository import MediaRepository
from app.i18n import t
from app.telegram.client import TelegramClient

logger = logging.getLogger(__name__)


class TelegramBot:
    """Asynchronous polling bot engine for Telegram."""

    def __init__(
        self,
        config: Config,
        telegram_client: TelegramClient,
        auth_middleware: AuthorizationMiddleware,
        command_handlers: CommandHandlers,
        message_handlers: MessageHandlers,
        repository: Optional[MediaRepository] = None,
    ) -> None:
        self.config = config
        self.client = telegram_client
        self.auth = auth_middleware
        self.commands = command_handlers
        self.messages = message_handlers
        self.repository = repository
        self._running = False
        self._last_update_id: Optional[int] = None

    async def start(self) -> None:
        """Starts the Telegram bot polling loop."""
        self._running = True
        logger.info("Verifying Telegram bot token...")
        try:
            bot_user = await self.client.get_me()
            logger.info("Bot authenticated as @%s (ID: %s)", bot_user.get("username"), bot_user.get("id"))
        except Exception as e:
            logger.error("Failed to authenticate with Telegram: %s", e)
            raise

        logger.info("Starting Telegram long-polling loop...")
        while self._running:
            try:
                offset = self._last_update_id + 1 if self._last_update_id else None
                updates = await self.client.get_updates(offset=offset, timeout=20)

                for update in updates:
                    update_id = update.get("update_id")
                    if update_id is not None:
                        self._last_update_id = update_id

                    await self._dispatch_update(update)

            except asyncio.CancelledError:
                logger.info("Telegram polling cancelled.")
                break
            except Exception as e:
                logger.error("Error during Telegram polling update: %s", e)
                await asyncio.sleep(self.config.poll_interval_seconds)

    def stop(self) -> None:
        """Stops the polling loop."""
        self._running = False
        logger.info("Stopping Telegram bot...")

    async def _dispatch_update(self, update: Dict[str, Any]) -> None:
        """Routes updates through auth middleware and to appropriate handlers."""
        # 1. Message update
        if "message" in update:
            message = update["message"]
            user = message.get("from", {})
            user_id = user.get("id")
            chat_id = message.get("chat", {}).get("id")

            # Check authorization
            if not self.auth.is_authorized(user_id):
                logger.warning("Unauthorized access attempt from user_id=%s (chat_id=%s)", user_id, chat_id)
                if chat_id:
                    await self.client.send_message(chat_id, self.auth.get_unauthorized_message(user_id))
                return

            # Authorized message handling
            await self.messages.handle_message(message)

        # 2. Callback query update (inline buttons & language switcher)
        elif "callback_query" in update:
            cb = update["callback_query"]
            user = cb.get("from", {})
            user_id = user.get("id")
            chat_id = cb.get("message", {}).get("chat", {}).get("id")
            data = cb.get("data", "")

            if not self.auth.is_authorized(user_id):
                return

            # Language selection callback
            if data.startswith("lang:") and chat_id and user_id:
                choice = data.split(":")[1]
                if self.repository:
                    await self.repository.set_user_language(user_id, choice)

                # Send confirmation with updated persistent reply keyboard
                conf_msg = t("lang_changed", choice)
                await self.client.send_message(
                    chat_id=chat_id,
                    text=conf_msg,
                    reply_markup=get_main_reply_keyboard(choice),
                )
                # Show welcome message in new language
                first_name = user.get("first_name", "")
                await self.commands.handle_start(chat_id, user_id=user_id, user_name=first_name)
                return

            # Request to change language from Settings menu
            if data == "change_lang" and chat_id and user_id:
                lang = (await self.repository.get_user_language(user_id)) if self.repository else "fa"
                prompt_text = t("choose_language_prompt", lang or "fa")
                await self.client.send_message(
                    chat_id=chat_id,
                    text=prompt_text,
                    reply_markup=get_language_inline_keyboard(),
                )
                return

            if data == "refresh_status" and chat_id:
                await self.commands.handle_status(chat_id, user_id=user_id)
