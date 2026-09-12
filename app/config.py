"""Configuration management for the Instagram Telegram Bot.

Loads configuration from environment variables and optional .env files.
Provides strong validation, secret masking, and sensible defaults.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Set


def load_dotenv(env_file_path: Path | str = ".env") -> None:
    """Lightweight .env loader without third-party dependencies."""
    path = Path(env_file_path)
    if not path.is_file():
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = val


@dataclass
class Config:
    telegram_bot_token: str
    authorized_telegram_user_ids: Set[int] = field(default_factory=set)
    instagram_account: str = ""
    instagram_username: str = ""
    instagram_password: str = ""
    instagram_session_id: str = ""
    instagram_auth_method: str = "graph_api"  # "graph_api", "oembed", "webhook", "mock"
    instagram_access_token: str = ""
    instagram_app_secret: str = ""
    instagram_verify_token: str = ""
    database_url: str = "sqlite:///data/bot.db"
    download_dir: Path = field(default_factory=lambda: Path("./downloads"))
    data_dir: Path = field(default_factory=lambda: Path("./data"))
    keep_downloads: bool = False
    max_download_size_bytes: int = 50 * 1024 * 1024  # 50 MB Telegram limit
    max_retries: int = 3
    retry_backoff_seconds: float = 2.0
    request_timeout_seconds: float = 30.0
    poll_interval_seconds: float = 2.0
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8000
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, env_path: Path | str = ".env") -> Config:
        load_dotenv(env_path)

        bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

        # Parse authorized telegram user IDs
        auth_users_raw = os.getenv("AUTHORIZED_TELEGRAM_USER_IDS", "")
        auth_users: Set[int] = set()
        for item in auth_users_raw.replace(";", ",").split(","):
            item = item.strip()
            if item:
                try:
                    auth_users.add(int(item))
                except ValueError:
                    logging.warning("Ignoring invalid Telegram user ID in config: %s", item)

        db_url = os.getenv("DATABASE_URL", "sqlite:///data/bot.db").strip()
        download_path = Path(os.getenv("DOWNLOAD_DIR", "./downloads")).resolve()
        data_path = Path(os.getenv("DATA_DIR", "./data")).resolve()

        keep_down = os.getenv("KEEP_DOWNLOADS", "false").lower() in ("true", "1", "yes")

        try:
            max_size = int(os.getenv("MAX_DOWNLOAD_SIZE_BYTES", str(50 * 1024 * 1024)))
        except ValueError:
            max_size = 50 * 1024 * 1024

        try:
            retries = int(os.getenv("MAX_RETRIES", "3"))
        except ValueError:
            retries = 3

        try:
            backoff = float(os.getenv("RETRY_BACKOFF_SECONDS", "2.0"))
        except ValueError:
            backoff = 2.0

        try:
            timeout = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30.0"))
        except ValueError:
            timeout = 30.0

        try:
            poll_interval = float(os.getenv("POLL_INTERVAL_SECONDS", "2.0"))
        except ValueError:
            poll_interval = 2.0

        try:
            webhook_port = int(os.getenv("WEBHOOK_PORT", "8000"))
        except ValueError:
            webhook_port = 8000

        ig_account = os.getenv("INSTAGRAM_ACCOUNT", "").strip()
        ig_username = os.getenv("INSTAGRAM_USERNAME", "").strip() or ig_account

        cfg = cls(
            telegram_bot_token=bot_token,
            authorized_telegram_user_ids=auth_users,
            instagram_account=ig_account or ig_username,
            instagram_username=ig_username,
            instagram_password=os.getenv("INSTAGRAM_PASSWORD", "").strip(),
            instagram_session_id=os.getenv("INSTAGRAM_SESSION_ID", "").strip(),
            instagram_auth_method=os.getenv("INSTAGRAM_AUTH_METHOD", "graph_api").strip(),
            instagram_access_token=os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip(),
            instagram_app_secret=os.getenv("INSTAGRAM_APP_SECRET", "").strip(),
            instagram_verify_token=os.getenv("INSTAGRAM_VERIFY_TOKEN", "").strip(),
            database_url=db_url,
            download_dir=download_path,
            data_dir=data_path,
            keep_downloads=keep_down,
            max_download_size_bytes=max_size,
            max_retries=retries,
            retry_backoff_seconds=backoff,
            request_timeout_seconds=timeout,
            poll_interval_seconds=poll_interval,
            webhook_host=os.getenv("WEBHOOK_HOST", "0.0.0.0").strip(),
            webhook_port=webhook_port,
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
        )

        cfg.download_dir.mkdir(parents=True, exist_ok=True)
        cfg.data_dir.mkdir(parents=True, exist_ok=True)

        return cfg

    def is_user_authorized(self, user_id: int) -> bool:
        if not self.authorized_telegram_user_ids:
            return False
        return user_id in self.authorized_telegram_user_ids

    def get_sqlite_path(self) -> str:
        if self.database_url.startswith("sqlite:///"):
            return self.database_url.replace("sqlite:///", "")
        if self.database_url.startswith("sqlite://"):
            return self.database_url.replace("sqlite://", "")
        return self.database_url

    def safe_repr(self) -> str:
        """Returns safe representation without revealing secrets."""
        masked_token = (
            f"{self.telegram_bot_token[:4]}...{self.telegram_bot_token[-4:]}"
            if len(self.telegram_bot_token) > 8
            else "[REDACTED]"
        )
        has_pwd = "[CONFIGURED]" if self.instagram_password else "[EMPTY]"
        has_sess = "[CONFIGURED]" if self.instagram_session_id else "[EMPTY]"

        return (
            f"Config("
            f"telegram_bot_token='{masked_token}', "
            f"authorized_users={list(self.authorized_telegram_user_ids)}, "
            f"instagram_username='{self.instagram_username}', "
            f"instagram_password={has_pwd}, "
            f"instagram_session_id={has_sess}, "
            f"database_url='{self.database_url}', "
            f"download_dir='{self.download_dir}', "
            f"keep_downloads={self.keep_downloads}, "
            f"max_download_size_bytes={self.max_download_size_bytes})"
        )
