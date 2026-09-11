"""Authorization verification middleware for Telegram interactions."""

from __future__ import annotations

import logging
from typing import Optional

from app.config import Config

logger = logging.getLogger(__name__)


class AuthorizationMiddleware:
    """Ensures only whitelisted Telegram user IDs can interact with the bot."""

    def __init__(self, config: Config) -> None:
        self.config = config

    def is_authorized(self, user_id: Optional[int]) -> bool:
        if user_id is None:
            return False
        return self.config.is_user_authorized(user_id)

    def get_unauthorized_message(self, user_id: Optional[int]) -> str:
        uid_str = str(user_id) if user_id is not None else "Unknown"
        return (
            "⛔ <b>Access Denied</b>\n\n"
            "This is a private personal Instagram downloader bot.\n"
            f"Your Telegram User ID is: <code>{uid_str}</code>\n\n"
            "To grant access, add your ID to <code>AUTHORIZED_TELEGRAM_USER_IDS</code> in the configuration."
        )
