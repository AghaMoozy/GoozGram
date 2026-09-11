"""Unit tests for Meta Webhook signature verification and DM payload processing."""

import hashlib
import hmac
import json
import unittest
from unittest.mock import AsyncMock

from app.config import Config
from app.instagram.webhook import InstagramWebhookHandler


class TestWebhook(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.cfg = Config(
            telegram_bot_token="test_token",
            instagram_app_secret="my_super_secret",
            instagram_verify_token="test_verify_token_xyz",
        )
        self.mock_callback = AsyncMock()
        self.handler = InstagramWebhookHandler(self.cfg, on_message_callback=self.mock_callback)

    def test_verify_challenge_success(self):
        query = "hub.mode=subscribe&hub.verify_token=test_verify_token_xyz&hub.challenge=11582012"
        challenge = self.handler.verify_challenge(query)
        self.assertEqual(challenge, "11582012")

    def test_verify_challenge_failure(self):
        query = "hub.mode=subscribe&hub.verify_token=wrong_token&hub.challenge=11582012"
        challenge = self.handler.verify_challenge(query)
        self.assertIsNone(challenge)

    def test_verify_signature(self):
        payload = b'{"object":"instagram","entry":[]}'
        sig = hmac.new(b"my_super_secret", payload, hashlib.sha256).hexdigest()
        header = f"sha256={sig}"

        self.assertTrue(self.handler.verify_signature(payload, header))
        self.assertFalse(self.handler.verify_signature(payload, "sha256=invalid_hash"))

    async def test_process_payload_with_extracted_urls(self):
        payload = {
            "object": "instagram",
            "entry": [
                {
                    "id": "178414000",
                    "time": 1720000000,
                    "messaging": [
                        {
                            "sender": {"id": "sender_123"},
                            "recipient": {"id": "my_account_id"},
                            "message": {
                                "mid": "m_123",
                                "text": "Check this reel https://www.instagram.com/reel/Cabc123/ now!",
                            },
                        }
                    ],
                }
            ],
        }
        body_bytes = json.dumps(payload).encode("utf-8")
        urls = await self.handler.process_payload(body_bytes)

        self.assertEqual(len(urls), 1)
        self.assertEqual(urls[0], "https://www.instagram.com/reel/Cabc123/")
        self.mock_callback.assert_awaited_once_with("https://www.instagram.com/reel/Cabc123/", "sender_123")


if __name__ == "__main__":
    unittest.main()
