"""Main application entry point, lifecycle manager, and webhook server."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import Optional

from app.bot.bot import TelegramBot
from app.bot.handlers.commands import CommandHandlers
from app.bot.handlers.messages import MessageHandlers
from app.bot.middlewares.auth import AuthorizationMiddleware
from app.config import Config
from app.database.repository import MediaRepository
from app.instagram.client import InstagramClient
from app.instagram.downloader import MediaDownloader
from app.instagram.webhook import InstagramWebhookHandler
from app.services.media_service import MediaService
from app.telegram.client import TelegramClient
from app.telegram.sender import TelegramMediaSender

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("app.main")


class WebhookServer:
    """Lightweight asynchronous HTTP server for Meta Webhooks."""

    def __init__(self, config: Config, webhook_handler: InstagramWebhookHandler) -> None:
        self.config = config
        self.handler = webhook_handler
        self._server: Optional[asyncio.Server] = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client,
            self.config.webhook_host,
            self.config.webhook_port,
        )
        addr = self._server.sockets[0].getsockname()
        logger.info("Instagram Webhook server listening on %s:%s", addr[0], addr[1])

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("Instagram Webhook server stopped")

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            line = await reader.readline()
            if not line:
                writer.close()
                return

            request_line = line.decode("utf-8").strip()
            parts = request_line.split(" ")
            if len(parts) < 2:
                writer.close()
                return

            method, path = parts[0], parts[1]

            # Read headers
            headers = {}
            while True:
                header_line = await reader.readline()
                if not header_line or header_line == b"\r\n":
                    break
                header_str = header_line.decode("utf-8").strip()
                if ":" in header_str:
                    k, v = header_str.split(":", 1)
                    headers[k.strip().lower()] = v.strip()

            content_length = int(headers.get("content-length", 0))
            body = await reader.readexactly(content_length) if content_length > 0 else b""

            # Route: GET /health
            if method == "GET" and path == "/health":
                self._send_response(writer, 200, "application/json", b'{"status":"healthy"}')
                return

            # Route: GET /webhook/instagram (Meta Challenge)
            if method == "GET" and "/webhook/instagram" in path:
                query_str = path.split("?", 1)[1] if "?" in path else ""
                challenge = self.handler.verify_challenge(query_str)
                if challenge:
                    self._send_response(writer, 200, "text/plain", challenge.encode("utf-8"))
                else:
                    self._send_response(writer, 403, "text/plain", b"Verification failed")
                return

            # Route: POST /webhook/instagram (Incoming DMs)
            if method == "POST" and "/webhook/instagram" in path:
                sig = headers.get("x-hub-signature-256", "")
                if not self.handler.verify_signature(body, sig):
                    logger.warning("Rejected webhook POST with invalid signature")
                    self._send_response(writer, 401, "text/plain", b"Invalid signature")
                    return

                # Process payload asynchronously
                asyncio.create_task(self.handler.process_payload(body))
                self._send_response(writer, 200, "text/plain", b"EVENT_RECEIVED")
                return

            # 404 for other routes
            self._send_response(writer, 404, "text/plain", b"Not Found")

        except Exception as e:
            logger.error("Error handling webhook request: %s", e)
        finally:
            try:
                await writer.drain()
                writer.close()
            except Exception:
                pass

    def _send_response(
        self, writer: asyncio.StreamWriter, status: int, content_type: str, body: bytes
    ) -> None:
        status_text = "OK" if status == 200 else ("Not Found" if status == 404 else "Error")
        res = (
            f"HTTP/1.1 {status} {status_text}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode("utf-8") + body
        writer.write(res)


async def main() -> None:
    """Initializes all components and manages application lifecycle."""
    config = Config.from_env()
    logging.getLogger().setLevel(config.log_level)
    logger.info("Initializing application with configuration: %s", config.safe_repr())

    if not config.telegram_bot_token:
        logger.critical("TELEGRAM_BOT_TOKEN is missing. Please configure it in .env.")
        sys.exit(1)

    if not config.authorized_telegram_user_ids:
        logger.warning(
            "AUTHORIZED_TELEGRAM_USER_IDS is empty. Nobody will be authorized to use the bot!"
        )

    # 1. Database layer
    repository = MediaRepository(config.get_sqlite_path())
    await repository.init_db()

    # 2. Instagram & Telegram clients
    instagram_client = InstagramClient(config)
    downloader = MediaDownloader(config)
    telegram_client = TelegramClient(config)
    sender = TelegramMediaSender(config, telegram_client)

    # 3. Media processing service
    media_service = MediaService(
        config=config,
        repository=repository,
        instagram_client=instagram_client,
        downloader=downloader,
        sender=sender,
        telegram_client=telegram_client,
    )

    # 4. Telegram Bot Handlers
    commands = CommandHandlers(config, telegram_client, repository)
    messages = MessageHandlers(telegram_client, media_service, commands)
    auth_middleware = AuthorizationMiddleware(config)
    bot = TelegramBot(config, telegram_client, auth_middleware, commands, messages)

    # 5. Instagram DM Webhook integration callback
    async def on_instagram_dm_url(url: str, sender_id: Optional[str]) -> None:
        logger.info("Instagram DM link received via webhook: %s (from sender %s)", url, sender_id)
        for user_id in config.authorized_telegram_user_ids:
            logger.info("Forwarding Instagram DM link to authorized Telegram user %s", user_id)
            await media_service.process_url(url, chat_id=user_id)

    webhook_handler = InstagramWebhookHandler(config, on_message_callback=on_instagram_dm_url)
    webhook_server = WebhookServer(config, webhook_handler)

    # 6. Graceful shutdown coordination
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _signal_handler():
        logger.info("Shutdown signal received.")
        stop_event.set()
        bot.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass

    # Start services
    await webhook_server.start()
    bot_task = asyncio.create_task(bot.start())

    logger.info("Personal Instagram Downloader Telegram Bot is running!")
    try:
        await stop_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("Shutting down services...")
        bot.stop()
        bot_task.cancel()
        await webhook_server.stop()
        await instagram_client.close()
        await downloader.close()
        await telegram_client.close()
        logger.info("All services shut down cleanly.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Application exited.")
