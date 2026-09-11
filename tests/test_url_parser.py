"""Unit tests for Instagram URL parsing and validation."""

import unittest

from app.instagram.models import ContentType
from app.instagram.parser import (
    InvalidInstagramURLError,
    UnsupportedInstagramURLError,
    extract_instagram_urls,
    parse_instagram_url,
)


class TestInstagramUrlParser(unittest.TestCase):

    def test_valid_post_urls(self):
        urls = [
            "https://www.instagram.com/p/C123abc/",
            "https://instagram.com/p/C123abc?igsh=NTc4MTIwNjQ2YQ==",
            "http://instagr.am/p/C123abc",
            "https://www.instagram.com/p/C123abc",
        ]
        for url in urls:
            parsed = parse_instagram_url(url)
            self.assertEqual(parsed.content_type, ContentType.POST)
            self.assertEqual(parsed.content_id, "C123abc")
            self.assertEqual(parsed.canonical_url, "https://www.instagram.com/p/C123abc/")

    def test_valid_reel_urls(self):
        urls = [
            "https://www.instagram.com/reel/C987xyz/",
            "https://www.instagram.com/reels/C987xyz?utm_source=ig_web_copy_link",
        ]
        for url in urls:
            parsed = parse_instagram_url(url)
            self.assertEqual(parsed.content_type, ContentType.REEL)
            self.assertEqual(parsed.content_id, "C987xyz")
            self.assertEqual(parsed.canonical_url, "https://www.instagram.com/reel/C987xyz/")

    def test_valid_story_urls(self):
        url = "https://www.instagram.com/stories/alireza/3312345678901234567/?utm_source=ig_story_item_share"
        parsed = parse_instagram_url(url)
        self.assertEqual(parsed.content_type, ContentType.STORY)
        self.assertEqual(parsed.username, "alireza")
        self.assertEqual(parsed.content_id, "alireza_3312345678901234567")
        self.assertEqual(parsed.canonical_url, "https://www.instagram.com/stories/alireza/3312345678901234567/")

    def test_invalid_domains(self):
        invalid_urls = [
            "https://twitter.com/p/C123abc",
            "https://fake-instagram.com/p/C123abc",
            "https://google.com",
            "not_a_url",
            "",
        ]
        for url in invalid_urls:
            with self.assertRaises(InvalidInstagramURLError):
                parse_instagram_url(url)

    def test_unsupported_urls(self):
        unsupported = [
            "https://www.instagram.com/explore/",
            "https://www.instagram.com/direct/inbox/",
            "https://www.instagram.com/elonmusk",
            "https://www.instagram.com/",
        ]
        for url in unsupported:
            with self.assertRaises(UnsupportedInstagramURLError):
                parse_instagram_url(url)

    def test_extract_urls_from_text(self):
        text = (
            "Hey check out this cool reel https://www.instagram.com/reel/C123456/ and "
            "also this post https://instagram.com/p/C789abc/?igsh=123 for later!"
        )
        found = extract_instagram_urls(text)
        self.assertEqual(len(found), 2)
        self.assertIn("https://www.instagram.com/reel/C123456/", found)


if __name__ == "__main__":
    unittest.main()


import hashlib
import hmac
import json
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


class TestWebhookServerLive(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        from app.main import WebhookServer
        self.cfg = Config(
            telegram_bot_token="dummy",
            instagram_verify_token="socket_challenge_token_456",
            webhook_host="127.0.0.1",
            webhook_port=8998,
        )
        self.handler = InstagramWebhookHandler(self.cfg)
        self.server = WebhookServer(self.cfg, self.handler)
        await self.server.start()

    async def asyncTearDown(self):
        await self.server.stop()

    async def test_live_health_and_challenge(self):
        import httpx
        async with httpx.AsyncClient() as client:
            res_health = await client.get("http://127.0.0.1:8998/health")
            self.assertEqual(res_health.status_code, 200)
            self.assertEqual(res_health.json(), {"status": "healthy"})

            res_challenge = await client.get(
                "http://127.0.0.1:8998/webhook/instagram",
                params={
                    "hub.mode": "subscribe",
                    "hub.verify_token": "socket_challenge_token_456",
                    "hub.challenge": "12345678",
                },
            )
            self.assertEqual(res_challenge.status_code, 200)
            self.assertEqual(res_challenge.text, "12345678")
