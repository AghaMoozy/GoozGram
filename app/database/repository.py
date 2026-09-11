"""Thread-safe and async-compatible SQLite repository for media tracking."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.database.models import DeliveryStatus, MediaRecord, MediaStatus

logger = logging.getLogger(__name__)


class MediaRepository:
    """Manages database persistence for Instagram media downloads and deliveries."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._init_db_sync()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.db_path),
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            check_same_thread=False,
            timeout=15.0,
        )
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db_sync(self) -> None:
        """Initializes tables and indexes synchronously on startup."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS media_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_id TEXT NOT NULL UNIQUE,
                    url TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    telegram_chat_id INTEGER,
                    telegram_message_id INTEGER,
                    delivery_status TEXT NOT NULL,
                    error_message TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_content_id ON media_records(content_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_status ON media_records(status)"
            )
            conn.commit()
            logger.info("Database initialized at %s", self.db_path)

    async def init_db(self) -> None:
        """Async initialization helper."""
        await asyncio.to_thread(self._init_db_sync)

    def _row_to_record(self, row: sqlite3.Row) -> MediaRecord:
        return MediaRecord(
            id=row["id"],
            content_id=row["content_id"],
            url=row["url"],
            media_type=row["media_type"],
            status=MediaStatus(row["status"]),
            telegram_chat_id=row["telegram_chat_id"],
            telegram_message_id=row["telegram_message_id"],
            delivery_status=DeliveryStatus(row["delivery_status"]),
            error_message=row["error_message"],
            retry_count=row["retry_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def get_by_content_id(self, content_id: str) -> Optional[MediaRecord]:
        def _get():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM media_records WHERE content_id = ?",
                    (content_id,),
                )
                row = cursor.fetchone()
                return self._row_to_record(row) if row else None

        return await asyncio.to_thread(_get)

    async def get_by_url(self, url: str) -> Optional[MediaRecord]:
        def _get():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM media_records WHERE url = ? ORDER BY id DESC LIMIT 1",
                    (url,),
                )
                row = cursor.fetchone()
                return self._row_to_record(row) if row else None

        return await asyncio.to_thread(_get)

    async def create_record(
        self,
        content_id: str,
        url: str,
        media_type: str = "unknown",
        telegram_chat_id: Optional[int] = None,
    ) -> MediaRecord:
        now_iso = datetime.now(timezone.utc).isoformat()

        def _create():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO media_records (
                        content_id, url, media_type, status,
                        telegram_chat_id, telegram_message_id,
                        delivery_status, error_message, retry_count,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        content_id,
                        url,
                        media_type,
                        MediaStatus.PENDING.value,
                        telegram_chat_id,
                        None,
                        DeliveryStatus.PENDING.value,
                        None,
                        0,
                        now_iso,
                        now_iso,
                    ),
                )
                conn.commit()
                record_id = cursor.lastrowid
                return MediaRecord(
                    id=record_id,
                    content_id=content_id,
                    url=url,
                    media_type=media_type,
                    status=MediaStatus.PENDING,
                    telegram_chat_id=telegram_chat_id,
                    created_at=now_iso,
                    updated_at=now_iso,
                )

        async with self._lock:
            return await asyncio.to_thread(_create)

    async def update_status(
        self,
        record_id: int,
        status: MediaStatus,
        error_message: Optional[str] = None,
        delivery_status: Optional[DeliveryStatus] = None,
        telegram_message_id: Optional[int] = None,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()

        def _update():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                params: List[Any] = [status.value]
                query_parts = ["status = ?"]

                if error_message is not None:
                    query_parts.append("error_message = ?")
                    params.append(error_message)

                if delivery_status is not None:
                    query_parts.append("delivery_status = ?")
                    params.append(delivery_status.value)

                if telegram_message_id is not None:
                    query_parts.append("telegram_message_id = ?")
                    params.append(telegram_message_id)

                query_parts.append("updated_at = ?")
                params.append(now_iso)

                params.append(record_id)
                query = f"UPDATE media_records SET {', '.join(query_parts)} WHERE id = ?"
                cursor.execute(query, params)
                conn.commit()

        async with self._lock:
            await asyncio.to_thread(_update)

    async def increment_retry(self, record_id: int) -> int:
        now_iso = datetime.now(timezone.utc).isoformat()

        def _increment():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE media_records
                    SET retry_count = retry_count + 1, updated_at = ?
                    WHERE id = ?
                    RETURNING retry_count
                    """,
                    (now_iso, record_id),
                )
                row = cursor.fetchone()
                conn.commit()
                return row[0] if row else 0

        async with self._lock:
            return await asyncio.to_thread(_increment)

    async def get_stats(self) -> Dict[str, Any]:
        def _stats():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT status, count(*) as count
                    FROM media_records
                    GROUP BY status
                """)
                counts = {row["status"]: row["count"] for row in cursor.fetchall()}
                cursor.execute("SELECT count(*) FROM media_records")
                total = cursor.fetchone()[0]
                return {
                    "total": total,
                    "by_status": counts,
                }

        return await asyncio.to_thread(_stats)
