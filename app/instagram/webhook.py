"""Official Meta Webhook receiver for Instagram Messaging API (Direct Messages).

Compliant with Meta Developer Webhooks for Instagram Messaging API.
Handles:
- GET challenge verification (hub.challenge, hub.verify_token)
- POST message notification with X-Hub-Signature-256 HMAC verification
- Link/attachment extraction from received DMs
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from app.config import Config
from app.instagram.parser import extract_instagram_urls

logger = logging.getLogger(__name__)


class InstagramWebhookHandler:
    """Processes incoming Meta webhook payloads for Instagram Direct Messages."""

    def __init__(
        self,
        config: Config,
        on_message_callback: Optional[Callable[[str, Optional[str]], Coroutine[Any, Any, None]]] = None,
    ) -> None:
        self.config = config
        self.on_message_callback = on_message_callback

    def verify_challenge(self, query_string: str) -> Optional[str]:
        """Validates Meta webhook subscription verification challenge."""
        if not self.config.instagram_verify_token:
            logger.warning("Rejecting Meta Webhook challenge: INSTAGRAM_VERIFY_TOKEN is not configured")
            return None

        params = parse_qs(query_string)
        mode = params.get("hub.mode", [""])[0]
        token = params.get("hub.verify_token", [""])[0]
        challenge = params.get("hub.challenge", [""])[0]

        if mode == "subscribe" and hmac.compare_digest(token, self.config.instagram_verify_token):
            logger.info("Meta Webhook verification challenge accepted")
            return challenge

        logger.warning("Meta Webhook verification challenge rejected. Token mismatch or bad mode.")
        return None

    def verify_signature(self, payload: bytes, signature_header: str) -> bool:
        """Verifies HMAC SHA-256 signature from Meta if app secret is configured."""
        if not self.config.instagram_app_secret:
            if self.config.instagram_auth_method == "mock":
                return True
            logger.error("Rejecting Webhook POST: INSTAGRAM_APP_SECRET is not configured for security")
            return False

        if not signature_header or not signature_header.startswith("sha256="):
            logger.warning("Missing or malformed X-Hub-Signature-256 header")
            return False

        expected_sig = signature_header[7:]
        computed_sig = hmac.new(
            self.config.instagram_app_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected_sig, computed_sig)

    async def process_payload(self, body_bytes: bytes) -> List[str]:
        """Parses Instagram messaging entries and extracts URLs."""
        try:
            data = json.loads(body_bytes.decode("utf-8"))
        except Exception as e:
            logger.error("Failed to decode webhook JSON: %s", e)
            return []

        extracted_urls: List[str] = []

        # Meta Instagram messaging structure
        entries = data.get("entry", [])
        for entry in entries:
            messaging_events = entry.get("messaging", [])
            for event in messaging_events:
                sender_id = event.get("sender", {}).get("id")
                message = event.get("message", {})

                # 1. Plain text messages with Instagram URLs
                text = message.get("text", "")
                if text:
                    urls = extract_instagram_urls(text)
                    for url in urls:
                        extracted_urls.append(url)
                        if self.on_message_callback:
                            await self.on_message_callback(url, sender_id)

                # 2. Shared attachments (shared posts, reels, stories in DMs)
                attachments = message.get("attachments", [])
                for att in attachments:
                    payload = att.get("payload", {})
                    url = payload.get("url")
                    if url:
                        urls = extract_instagram_urls(url)
                        for u in urls:
                            extracted_urls.append(u)
                            if self.on_message_callback:
                                await self.on_message_callback(u, sender_id)

        return extracted_urls
