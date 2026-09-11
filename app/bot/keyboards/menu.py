"""Keyboards and menu layouts for the Telegram bot interface."""

from __future__ import annotations

from typing import Any, Dict


def get_main_reply_keyboard() -> Dict[str, Any]:
    """Returns a simple, clean reply keyboard for quick access to commands."""
    return {
        "keyboard": [
            [{"text": "📊 Status"}, {"text": "⚙️ Settings"}],
            [{"text": "ℹ️ Help"}, {"text": "❌ Cancel"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }


def get_settings_inline_keyboard() -> Dict[str, Any]:
    """Inline keyboard for settings view."""
    return {
        "inline_keyboard": [
            [
                {"text": "🔄 Refresh Status", "callback_data": "refresh_status"},
                {"text": "📖 Documentation", "url": "https://github.com/ExclaveNetwork/Exclave"},
            ]
        ]
    }
