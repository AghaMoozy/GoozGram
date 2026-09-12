"""Telegram Bot command handlers with bilingual Persian/English support."""

from __future__ import annotations

import html
import logging
from typing import Any, Dict, Optional

from app.bot.keyboards.menu import (
    get_language_inline_keyboard,
    get_main_reply_keyboard,
    get_settings_inline_keyboard,
)
from app.config import Config
from app.database.repository import MediaRepository
from app.i18n import t
from app.telegram.client import TelegramClient

logger = logging.getLogger(__name__)


class CommandHandlers:
    """Handles Telegram standard slash commands with localization."""

    def __init__(
        self,
        config: Config,
        telegram_client: TelegramClient,
        repository: MediaRepository,
    ) -> None:
        self.config = config
        self.client = telegram_client
        self.repository = repository

    async def handle_start(
        self, chat_id: int, user_id: Optional[int] = None, user_name: str = ""
    ) -> None:
        uid = user_id or chat_id
        lang = await self.repository.get_user_language(uid)

        # 1. First time user: Prompt to choose Persian or English
        if lang is None:
            prompt_text = t("start_choose_lang", "fa")
            await self.client.send_message(
                chat_id=chat_id,
                text=prompt_text,
                reply_markup=get_language_inline_keyboard(),
            )
            return

        # 2. Returning user: Show welcome message in selected language
        clean_name = html.escape(user_name)
        greeting = f", <b>{clean_name}</b>" if clean_name else ""
        text = t("start_welcome", lang, greeting=greeting)

        await self.client.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=get_main_reply_keyboard(lang),
        )

    async def handle_help(self, chat_id: int, user_id: Optional[int] = None) -> None:
        uid = user_id or chat_id
        lang = await self.repository.get_user_language(uid) or "fa"
        await self.client.send_message(
            chat_id=chat_id,
            text=t("help_text", lang),
        )

    async def handle_status(self, chat_id: int, user_id: Optional[int] = None) -> None:
        uid = user_id or chat_id
        lang = await self.repository.get_user_language(uid) or "fa"

        stats = await self.repository.get_stats()
        total = stats.get("total", 0)
        by_status = stats.get("by_status", {})

        storage_mode = (
            "دائمی" if self.config.keep_downloads else "پاکسازی خودکار امن"
            if lang == "fa"
            else ("Keep files" if self.config.keep_downloads else "Auto-cleanup (Secure)")
        )

        text = t(
            "status_text",
            lang,
            total=total,
            sent=by_status.get("SENT", 0),
            downloading=by_status.get("DOWNLOADING", 0),
            pending=by_status.get("PENDING", 0),
            downloaded=by_status.get("DOWNLOADED", 0),
            failed=by_status.get("FAILED", 0),
            storage_mode=storage_mode,
            folder=html.escape(self.config.download_dir.name),
        )
        await self.client.send_message(chat_id=chat_id, text=text)

    async def handle_settings(self, chat_id: int, user_id: Optional[int] = None) -> None:
        uid = user_id or chat_id
        lang = await self.repository.get_user_language(uid) or "fa"

        auth_count = len(self.config.authorized_telegram_user_ids)
        max_size_mb = self.config.max_download_size_bytes / (1024 * 1024)
        db_file = html.escape(self.config.get_sqlite_path())

        cleanup_mode = (
            "غیرفعال" if self.config.keep_downloads else "فعال (حذف فوری پس از ارسال)"
            if lang == "fa"
            else ("Disabled" if self.config.keep_downloads else "Enabled (Immediate deletion)")
        )

        text = t(
            "settings_text",
            lang,
            auth_count=auth_count,
            max_size_mb=max_size_mb,
            cleanup_mode=cleanup_mode,
            db_file=db_file,
        )

        await self.client.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=get_settings_inline_keyboard(lang),
        )

    async def handle_cancel(self, chat_id: int, user_id: Optional[int] = None) -> None:
        uid = user_id or chat_id
        lang = await self.repository.get_user_language(uid) or "fa"
        await self.client.send_message(chat_id=chat_id, text=t("cancel_text", lang))
