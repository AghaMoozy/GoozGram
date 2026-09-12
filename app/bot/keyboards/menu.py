"""Keyboards and menu layouts for the Telegram bot interface (Persian & English)."""

from __future__ import annotations

from typing import Any, Dict


def get_main_reply_keyboard(lang: str = "fa") -> Dict[str, Any]:
    """Returns the persistent reply keyboard in user's selected language."""
    if lang == "en":
        return {
            "keyboard": [
                [{"text": "📊 Status"}, {"text": "⚙️ Settings"}],
                [{"text": "ℹ️ Help"}, {"text": "❌ Cancel"}],
            ],
            "resize_keyboard": True,
            "one_time_keyboard": False,
        }

    # Default Persian (فارسی)
    return {
        "keyboard": [
            [{"text": "📊 وضعیت"}, {"text": "⚙️ تنظیمات"}],
            [{"text": "ℹ️ راهنما"}, {"text": "❌ لغو"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }


def get_language_inline_keyboard() -> Dict[str, Any]:
    """Inline keyboard for choosing language (First-start or Settings)."""
    return {
        "inline_keyboard": [
            [
                {"text": "🇮🇷 فارسی", "callback_data": "lang:fa"},
                {"text": "🇬🇧 English", "callback_data": "lang:en"},
            ]
        ]
    }


def get_settings_inline_keyboard(lang: str = "fa") -> Dict[str, Any]:
    """Inline keyboard for settings view with language switch and refresh buttons."""
    refresh_text = "🔄 Refresh Status" if lang == "en" else "🔄 تازه‌سازی وضعیت"
    lang_btn_text = "🌐 Change Language" if lang == "en" else "🌐 تغییر زبان (Language)"

    return {
        "inline_keyboard": [
            [
                {"text": lang_btn_text, "callback_data": "change_lang"},
                {"text": refresh_text, "callback_data": "refresh_status"},
            ]
        ]
    }
