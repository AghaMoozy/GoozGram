"""Asynchronous Telegram Bot API client built on httpx."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from app.config import Config

logger = logging.getLogger(__name__)


class TelegramAPIError(Exception):
    """Exception raised when Telegram API returns an error or fails."""


class TelegramRateLimitError(TelegramAPIError):
    """Exception raised when Telegram returns HTTP 429 Too Many Requests."""

    def __init__(self, message: str, retry_after: int = 1) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class TelegramClient:
    """Asynchronous client interacting with official Telegram Bot API."""

    API_BASE = "https://api.telegram.org"

    def __init__(self, config: Config, http_client: Optional[httpx.AsyncClient] = None) -> None:
        self.config = config
        self._http_client = http_client
        self._owns_http_client = http_client is None
        self.token = config.telegram_bot_token

    @property
    def base_url(self) -> str:
        return f"{self.API_BASE}/bot{self.token}"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=60.0,
                headers={"User-Agent": "PersonalInstagramBot/1.0"},
            )
        return self._http_client

    async def close(self) -> None:
        if self._owns_http_client and self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    def _check_response(self, resp_data: Dict[str, Any], action: str) -> Dict[str, Any]:
        """Validates API JSON response and checks for rate limits."""
        if not resp_data.get("ok"):
            err_code = resp_data.get("error_code")
            desc = resp_data.get("description", "Unknown error")
            if err_code == 429:
                retry_after = resp_data.get("parameters", {}).get("retry_after", 1)
                raise TelegramRateLimitError(
                    f"Telegram rate limit encountered: {desc}", retry_after=retry_after
                )
            raise TelegramAPIError(f"Telegram {action} failed: {desc}")
        return resp_data.get("result", {})

    async def get_me(self) -> Dict[str, Any]:
        """Tests the token and returns bot profile info."""
        client = await self._get_client()
        resp = await client.get(f"{self.base_url}/getMe")
        return self._check_response(resp.json(), "getMe")

    async def get_updates(
        self, offset: Optional[int] = None, timeout: int = 20, allowed_updates: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Long-polling for updates."""
        client = await self._get_client()
        params: Dict[str, Any] = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        if allowed_updates:
            params["allowed_updates"] = json.dumps(allowed_updates)

        try:
            resp = await client.get(f"{self.base_url}/getUpdates", params=params, timeout=timeout + 10)
            data = resp.json()
            if not data.get("ok"):
                raise TelegramAPIError(f"Telegram getUpdates failed: {data.get('description')}")
            return data.get("result", [])
        except httpx.RequestError as e:
            logger.warning("Telegram polling connection error: %s", e)
            return []

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        parse_mode: str = "HTML",
        reply_to_message_id: Optional[int] = None,
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Sends a text message."""
        client = await self._get_client()
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)

        resp = await client.post(f"{self.base_url}/sendMessage", json=payload)
        return self._check_response(resp.json(), "sendMessage")

    async def delete_message(self, chat_id: int | str, message_id: int) -> bool:
        """Deletes a message from a chat."""
        try:
            client = await self._get_client()
            resp = await client.post(
                f"{self.base_url}/deleteMessage",
                json={"chat_id": chat_id, "message_id": message_id},
            )
            data = resp.json()
            return bool(data.get("ok", False))
        except Exception as e:
            logger.debug("Failed to delete message %s in chat %s: %s", message_id, chat_id, e)
            return False

    async def send_photo(
        self,
        chat_id: int | str,
        photo_path: Path,
        caption: Optional[str] = None,
        parse_mode: str = "HTML",
    ) -> Dict[str, Any]:
        """Sends a single photo file."""
        client = await self._get_client()
        data: Dict[str, Any] = {"chat_id": str(chat_id), "parse_mode": parse_mode}
        if caption:
            data["caption"] = caption

        with open(photo_path, "rb") as f:
            files = {"photo": (photo_path.name, f, "image/jpeg")}
            resp = await client.post(f"{self.base_url}/sendPhoto", data=data, files=files)

        return self._check_response(resp.json(), "sendPhoto")

    async def send_video(
        self,
        chat_id: int | str,
        video_path: Path,
        caption: Optional[str] = None,
        parse_mode: str = "HTML",
        supports_streaming: bool = True,
    ) -> Dict[str, Any]:
        """Sends a video file."""
        client = await self._get_client()
        data: Dict[str, Any] = {
            "chat_id": str(chat_id),
            "parse_mode": parse_mode,
            "supports_streaming": "true" if supports_streaming else "false",
        }
        if caption:
            data["caption"] = caption

        with open(video_path, "rb") as f:
            files = {"video": (video_path.name, f, "video/mp4")}
            resp = await client.post(f"{self.base_url}/sendVideo", data=data, files=files)

        return self._check_response(resp.json(), "sendVideo")

    async def send_document(
        self,
        chat_id: int | str,
        document_path: Path,
        caption: Optional[str] = None,
        parse_mode: str = "HTML",
    ) -> Dict[str, Any]:
        """Sends a general document / file as fallback."""
        client = await self._get_client()
        data: Dict[str, Any] = {"chat_id": str(chat_id), "parse_mode": parse_mode}
        if caption:
            data["caption"] = caption

        with open(document_path, "rb") as f:
            files = {"document": (document_path.name, f, "application/octet-stream")}
            resp = await client.post(f"{self.base_url}/sendDocument", data=data, files=files)

        return self._check_response(resp.json(), "sendDocument")

    async def send_media_group(
        self,
        chat_id: int | str,
        media_group: List[Dict[str, Any]],
        file_map: Dict[str, Path],
    ) -> List[Dict[str, Any]]:
        """Sends an album/carousel of photos and videos."""
        client = await self._get_client()
        data = {
            "chat_id": str(chat_id),
            "media": json.dumps(media_group),
        }

        opened_files = []
        files = {}
        try:
            for attach_name, file_path in file_map.items():
                f = open(file_path, "rb")
                opened_files.append(f)
                mime = "video/mp4" if file_path.suffix.lower() == ".mp4" else "image/jpeg"
                files[attach_name] = (file_path.name, f, mime)

            resp = await client.post(f"{self.base_url}/sendMediaGroup", data=data, files=files)
            return self._check_response(resp.json(), "sendMediaGroup")
        finally:
            for f in opened_files:
                f.close()
