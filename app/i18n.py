"""Localization and multi-language support (Persian & English)."""

from __future__ import annotations

from typing import Any, Dict

MESSAGES: Dict[str, Dict[str, str]] = {
    "start_choose_lang": {
        "fa": (
            "👋 <b>سلام! به ربات اختصاصی دانلودر اینستاگرام خوش آمدید.</b>\n\n"
            "لطفاً زبان مورد نظر خود را انتخاب کنید:\n"
            "Please select your preferred language:"
        ),
        "en": (
            "👋 <b>Welcome to your Personal Instagram Downloader Bot!</b>\n\n"
            "Please select your preferred language:\n"
            "لطفاً زبان مورد نظر خود را انتخاب کنید:"
        ),
    },
    "start_welcome": {
        "fa": (
            "👋 <b>به ربات شخصی دانلودر اینستاگرام خوش آمدید{greeting}!</b>\n\n"
            "این ربات به صورت کاملاً اختصاصی برای استفاده امن شما پیکربندی شده است.\n\n"
            "<b>روش استفاده:</b>\n"
            "۱. هر لینک پست، ریلز یا آلبوم اینستاگرام را مستقیماً به این چت بفرستید.\n"
            "۲. ربات فایل باکیفیت را دانلود کرده و در همین چت تحویل می‌دهد.\n\n"
            "<b>دستورات سریع:</b>\n"
            "• /status - مشاهده آمار و صف دانلود\n"
            "• /settings - تنظیمات و تغییر زبان\n"
            "• /help - راهنما و فرمت‌های پشتیبانی‌شده\n"
            "• /cancel - لغو عملیات جاری"
        ),
        "en": (
            "👋 <b>Welcome to your Personal Instagram Downloader{greeting}!</b>\n\n"
            "This bot is configured for your private, authorized use.\n\n"
            "<b>How to use:</b>\n"
            "1. Send or forward any Instagram Post, Reel, Story, or Carousel URL directly to this chat.\n"
            "2. The bot will automatically validate, download, and deliver the media here.\n\n"
            "<b>Quick Commands:</b>\n"
            "• /status - View download statistics and queue\n"
            "• /settings - View configuration & change language\n"
            "• /help - Usage guide and supported formats\n"
            "• /cancel - Reset or cancel pending operations"
        ),
    },
    "help_text": {
        "fa": (
            "📖 <b>راهنمای کامل استفاده از ربات</b>\n\n"
            "<b>محتواهای پشتیبانی‌شده:</b>\n"
            "• <b>پست‌ها</b>: تصاویر و ویدیوهای تک‌فایلی (<code>/p/SHORTCODE/</code>)\n"
            "• <b>ریلزها</b>: ویدیوهای کامل ریلز (<code>/reel/SHORTCODE/</code>)\n"
            "• <b>کاروسل‌ها</b>: آلبوم‌های اسلایدی چندتایی به صورت یکپارچه (Media Group)\n"
            "• <b>استوری‌ها</b>: استوری‌های فعال و منقضی‌نشده\n\n"
            "<b>محدودیت‌های تلگرام:</b>\n"
            "• ویدیوها و فایل‌ها: حداکثر تا ۵۰ مگابایت\n"
            "• تصاویر: حداکثر تا ۲۰ مگابایت\n"
            "• آلبوم‌ها: دسته‌بندی در بسته‌های حداکثر ۱۰تایی\n\n"
            "<i>کافیست لینک هر ویدیویی را کپی کنید و اینجا بفرستید!</i>"
        ),
        "en": (
            "📖 <b>User Guide & Documentation</b>\n\n"
            "<b>Supported Instagram Content:</b>\n"
            "• <b>Posts</b>: Single image or video (<code>/p/SHORTCODE/</code>)\n"
            "• <b>Reels</b>: Full-length video reels (<code>/reel/SHORTCODE/</code>)\n"
            "• <b>Carousels</b>: Multi-photo/video albums delivered as Telegram Media Groups\n"
            "• <b>Stories</b>: Active stories for authorized accounts\n\n"
            "<b>Telegram Limits:</b>\n"
            "• Videos & Documents: up to 50 MB\n"
            "• Photos: up to 20 MB\n"
            "• Albums: delivered in groups of up to 10 items\n\n"
            "<i>Simply paste any link to start downloading!</i>"
        ),
    },
    "status_text": {
        "fa": (
            "📊 <b>وضعیت و آمار ربات</b>\n\n"
            "• <b>تعداد کل درخواست‌ها:</b> {total}\n"
            "• <b>با موفقیت تحویل داده شده:</b> {sent} ✅\n"
            "• <b>در حال دانلود:</b> {downloading} ⏳\n"
            "• <b>در صف پردازش:</b> {pending}\n"
            "• <b>آماده ارسال:</b> {downloaded}\n"
            "• <b>درخواست‌های ناموفق:</b> {failed} ❌\n\n"
            "• <b>وضعیت ذخیره‌سازی:</b> {storage_mode}\n"
            "• <b>پوشه موقت:</b> <code>{folder}/</code>"
        ),
        "en": (
            "📊 <b>Bot Status & Statistics</b>\n\n"
            "• <b>Total Requests:</b> {total}\n"
            "• <b>Successfully Delivered:</b> {sent} ✅\n"
            "• <b>Currently Downloading:</b> {downloading} ⏳\n"
            "• <b>Pending In Queue:</b> {pending}\n"
            "• <b>Ready for Delivery:</b> {downloaded}\n"
            "• <b>Failed Requests:</b> {failed} ❌\n\n"
            "• <b>Storage Mode:</b> {storage_mode}\n"
            "• <b>Download Folder:</b> <code>{folder}/</code>"
        ),
    },
    "settings_text": {
        "fa": (
            "⚙️ <b>تنظیمات جاری سیستم</b>\n\n"
            "• <b>زبان فعلی:</b> 🇮🇷 فارسی\n"
            "• <b>تعداد کاربران مجاز:</b> {auth_count} کاربر\n"
            "• <b>موتور دانلود:</b> هوشمند چندلایه (yt-dlp + Web)\n"
            "• <b>حداکثر حجم مجاز:</b> {max_size_mb:.1f} مگابایت\n"
            "• <b>پاکسازی خودکار:</b> {cleanup_mode}\n"
            "• <b>پایگاه داده:</b> <code>{db_file}</code>"
        ),
        "en": (
            "⚙️ <b>Current System Configuration</b>\n\n"
            "• <b>Current Language:</b> 🇬🇧 English\n"
            "• <b>Authorized Telegram Users:</b> {auth_count} user(s)\n"
            "• <b>Download Engine:</b> Multi-layer (yt-dlp + Web)\n"
            "• <b>Max File Size:</b> {max_size_mb:.1f} MB\n"
            "• <b>Auto Cleanup:</b> {cleanup_mode}\n"
            "• <b>Database:</b> <code>{db_file}</code>"
        ),
    },
    "cancel_text": {
        "fa": "❌ <b>عملیات لغو شد.</b> هر زمان مایل بودید لینک جدیدی ارسال کنید.",
        "en": "❌ <b>Operations Cancelled.</b> You can send a new Instagram link anytime.",
    },
    "no_link_detected": {
        "fa": (
            "ℹ️ <b>لینکی در پیام شما شناسایی نشد</b>\n\n"
            "لطفاً یک لینک معتبر از اینستاگرام ارسال کنید، مانند:\n"
            "<code>https://www.instagram.com/reel/C123abc/</code>"
        ),
        "en": (
            "ℹ️ <b>No Instagram link detected</b>\n\n"
            "Please send a valid Instagram link (Post, Reel, Carousel, or Story), e.g.:\n"
            "<code>https://www.instagram.com/reel/C123abc/</code>"
        ),
    },
    "resolving_media": {
        "fa": "🔍 در حال بررسی و دریافت رسانه <code>{content_id}</code>...",
        "en": "🔍 Resolving media for <code>{content_id}</code>...",
    },
    "already_processed": {
        "fa": "ℹ️ <b>قبلاً ارسال شده</b>\n\nاین مدیا (<code>{content_id}</code>) قبلاً دانلود و برای شما ارسال شده است.",
        "en": "ℹ️ <b>Already Processed</b>\n\nThis Instagram media (<code>{content_id}</code>) was already downloaded and sent to you.",
    },
    "in_progress": {
        "fa": "⏳ <b>در حال انجام</b>\n\nاین مدیا هم‌اکنون در حال دانلود است. لطفاً کمی صبر کنید...",
        "en": "⏳ <b>In Progress</b>\n\nThis media is currently being downloaded. Please wait a moment...",
    },
    "lang_changed": {
        "fa": "🇮🇷 زبان ربات با موفقیت روی <b>فارسی</b> تنظیم شد.",
        "en": "🇬🇧 Bot language has been set to <b>English</b>.",
    },
    "choose_language_prompt": {
        "fa": "🌐 لطفاً زبان جدید ربات را انتخاب کنید:",
        "en": "🌐 Please select your new language:",
    },
    "caption_downloaded": {
        "fa": "<b>مدیای اینستاگرام با موفقیت دانلود شد</b>\n",
        "en": "<b>Instagram media downloaded successfully</b>\n",
    },
    "caption_source": {
        "fa": "<b>منبع:</b>",
        "en": "<b>Source:</b>",
    },
    "caption_url": {
        "fa": "<b>لینک:</b>",
        "en": "<b>URL:</b>",
    },
    "caption_title": {
        "fa": "<b>کپشن:</b>",
        "en": "<b>Caption:</b>",
    },
    "err_invalid_url": {
        "fa": "❌ <b>لینک اینستاگرام نامعتبر است</b>\n\n{err}",
        "en": "❌ <b>Invalid Instagram URL</b>\n\n{err}",
    },
    "err_unsupported_url": {
        "fa": "⚠️ <b>لینک پشتیبانی نمی‌شود</b>\n\n{err}\n\nپشتیبانی: پست، ریلز، آلبوم و استوری.",
        "en": "⚠️ <b>Unsupported Instagram Link</b>\n\n{err}\n\nSupported: Posts, Reels, Carousels, and Stories.",
    },
    "err_file_size": {
        "fa": (
            "⚠️ <b>حجم فایل بیش از حد مجاز است</b>\n\n"
            "حجم فایل ({size:.1f} مگابایت) از سقف ۵۰ مگابایت مجاز ربات‌های تلگرام بیشتر است.\n\n"
            "<b>لینک مستقیم:</b> {url}"
        ),
        "en": (
            "⚠️ <b>File Size Limit Exceeded</b>\n\n"
            "The media file ({size:.1f} MB) exceeds Telegram's bot upload limit of 50 MB.\n\n"
            "<b>Direct link:</b> {url}"
        ),
    },
    "err_content_unavailable": {
        "fa": "❌ <b>محتوا در دسترس نیست</b>\n\nاین پست یا ریلز ممکن است حذف شده باشد یا وجود نداشته باشد.",
        "en": "❌ <b>Content Unavailable</b>\n\nThis post has been deleted or does not exist.",
    },
    "err_private_account": {
        "fa": "🔒 <b>محتوای خصوصی یا محدودشده</b>\n\nاین محتوا مربوط به یک اکانت خصوصی است یا دسترسی به آن محدود شده است.",
        "en": "🔒 <b>Authentication / Permission Required</b>\n\nThis content is from a private account or requires login.",
    },
}


def t(key: str, lang: str = "fa", **kwargs: Any) -> str:
    """Translates a message key to the requested language (defaults to 'fa')."""
    lang_dict = MESSAGES.get(key, {})
    template = lang_dict.get(lang) or lang_dict.get("en") or key
    if kwargs:
        try:
            return template.format(**kwargs)
        except Exception:
            return template
    return template
