"""Telegram Bot command handlers (/start, /help, /status, /settings, /cancel)."""

from __future__ import annotations

import html
import logging
from typing import Any, Dict

from app.bot.keyboards.menu import get_main_reply_keyboard, get_settings_inline_keyboard
from app.config import Config
from app.database.repository import MediaRepository
from app.telegram.client import TelegramClient

logger = logging.getLogger(__name__)


class CommandHandlers:
    """Handles Telegram standard slash commands."""

    def __init__(
        self,
        config: Config,
        telegram_client: TelegramClient,
        repository: MediaRepository,
    ) -> None:
        self.config = config
        self.client = telegram_client
        self.repository = repository

    async def handle_start(self, chat_id: int, user_name: str = "") -> None:
        clean_name = html.escape(user_name)
        greeting = f", <b>{clean_name}</b>" if clean_name else ""
        text = (
            f"👋 <b>Welcome to your Personal Instagram Downloader{greeting}!</b>\n\n"
            "This bot is configured for your private, authorized use.\n\n"
            "<b>How to use:</b>\n"
            "1. Send or forward any Instagram Post, Reel, Story, or Carousel URL directly to this chat.\n"
            "2. Or, if configured with Meta Webhooks, send links to your controlled Instagram account via DM.\n"
            "3. The bot will automatically validate, download, and deliver the media here.\n\n"
            "<b>Quick Commands:</b>\n"
            "• /status - View download statistics and queue\n"
            "• /settings - View configuration and storage info\n"
            "• /help - Usage guide and supported formats\n"
            "• /cancel - Reset or cancel pending operations"
        )
        await self.client.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=get_main_reply_keyboard(),
        )

    async def handle_help(self, chat_id: int) -> None:
        text = (
            "📖 <b>User Guide & Documentation</b>\n\n"
            "<b>Supported Instagram Content:</b>\n"
            "• <b>Posts</b>: Single image or video (<code>/p/SHORTCODE/</code>)\n"
            "• <b>Reels</b>: Full-length video reels (<code>/reel/SHORTCODE/</code>)\n"
            "• <b>Carousels</b>: Multi-photo/video albums delivered as Telegram Media Groups\n"
            "• <b>Stories</b>: Active stories for authorized accounts (<code>/stories/USER/ID/</code>)\n\n"
            "<b>Content & Privacy Policy:</b>\n"
            "• Public content is resolved via official Meta endpoints.\n"
            "• Private content requires authorized access token configuration.\n"
            "• Expired stories (>24h) and deleted posts cannot be resolved.\n"
            "• No credentials, cookies, or unauthorized bypasses are used.\n\n"
            "<b>Telegram Limits:</b>\n"
            "• Videos & Documents: up to 50 MB\n"
            "• Photos: up to 20 MB\n"
            "• Albums: delivered in groups of up to 10 items\n\n"
            "<i>Simply paste any link to start downloading!</i>"
        )
        await self.client.send_message(chat_id=chat_id, text=text)

    async def handle_status(self, chat_id: int) -> None:
        stats = await self.repository.get_stats()
        total = stats.get("total", 0)
        by_status = stats.get("by_status", {})

        sent = by_status.get("SENT", 0)
        failed = by_status.get("FAILED", 0)
        pending = by_status.get("PENDING", 0)
        downloading = by_status.get("DOWNLOADING", 0)
        downloaded = by_status.get("DOWNLOADED", 0)

        text = (
            "📊 <b>Bot Status & Statistics</b>\n\n"
            f"• <b>Total Requests:</b> {total}\n"
            f"• <b>Successfully Delivered:</b> {sent} ✅\n"
            f"• <b>Currently Downloading:</b> {downloading} ⏳\n"
            f"• <b>Pending In Queue:</b> {pending}\n"
            f"• <b>Ready for Delivery:</b> {downloaded}\n"
            f"• <b>Failed Requests:</b> {failed} ❌\n\n"
            f"• <b>Storage Mode:</b> {'Keep files' if self.config.keep_downloads else 'Auto-cleanup (Secure)'}\n"
            f"• <b>Download Folder:</b> <code>{html.escape(self.config.download_dir.name)}/</code>"
        )
        await self.client.send_message(chat_id=chat_id, text=text)

    async def handle_settings(self, chat_id: int) -> None:
        auth_count = len(self.config.authorized_telegram_user_ids)
        max_size_mb = self.config.max_download_size_bytes / (1024 * 1024)
        db_file = html.escape(self.config.get_sqlite_path())
        account = html.escape(self.config.instagram_account or "Not specified")

        text = (
            "⚙️ <b>Current System Configuration</b>\n\n"
            f"• <b>Authorized Telegram Users:</b> {auth_count} user(s)\n"
            f"• <b>Instagram Account:</b> <code>{account}</code>\n"
            f"• <b>Instagram Auth Method:</b> <code>{html.escape(self.config.instagram_auth_method)}</code>\n"
            f"• <b>Access Token:</b> {'Configured' if self.config.instagram_access_token else 'None (Public/oEmbed mode)'}\n"
            f"• <b>Max File Size:</b> {max_size_mb:.1f} MB\n"
            f"• <b>Auto Cleanup:</b> {'Disabled' if self.config.keep_downloads else 'Enabled (Immediate deletion)'}\n"
            f"• <b>Max Retries:</b> {self.config.max_retries}\n"
            f"• <b>Database:</b> <code>{db_file}</code>\n"
            f"• <b>Log Level:</b> <code>{html.escape(self.config.log_level)}</code>"
        )
        await self.client.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=get_settings_inline_keyboard(),
        )

    async def handle_cancel(self, chat_id: int) -> None:
        text = (
            "❌ <b>Operations Cancelled</b>\n\n"
            "Any ongoing conversational prompts have been cleared.\n"
            "You can send a new Instagram link anytime."
        )
        await self.client.send_message(chat_id=chat_id, text=text)
