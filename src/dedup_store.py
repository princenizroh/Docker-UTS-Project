import sqlite3
import logging
import os
from datetime import datetime
from typing import Optional, Set, List, Tuple
import asyncio
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class DedupStore:
    """
    Persistent deduplication store menggunakan SQLite.

    Store ini menyimpan (topic, event_id) untuk mencegah pemrosesan duplikat.
    Desain ini mendukung:
    - Idempotency: event dengan (topic, event_id) sama hanya diproses sekali
    - Persistence: data tetap ada setelah restart
    - Thread-safe: menggunakan lock untuk concurrent access
    """

    def __init__(self, db_path: str = "dedup_store.db"):
        """
        Inisialisasi dedup store.

        Args:
            db_path: Path ke file database SQLite
        """
        self.db_path = db_path
        self.lock = asyncio.Lock()
        self._init_db()
        logger.info(f"DedupStore initialized with database: {db_path}")

    def _init_db(self):
        """
        Inisialisasi database dan tabel.
        Membuat tabel jika belum ada.
        """
        # Create directory if it doesn't exist
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            logger.info(f"Created database directory: {db_dir}")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                event_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL,
                payload TEXT NOT NULL,
                processed_at TEXT NOT NULL,
                UNIQUE(topic, event_id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_topic_event
            ON processed_events(topic, event_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_topic
            ON processed_events(topic)
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                received INTEGER DEFAULT 0,
                unique_processed INTEGER DEFAULT 0,
                duplicate_dropped INTEGER DEFAULT 0
            )
        """)

        cursor.execute("""
            INSERT OR IGNORE INTO stats (id, received, unique_processed, duplicate_dropped)
            VALUES (1, 0, 0, 0)
        """)

        conn.commit()
        conn.close()
        logger.info("Database tables initialized successfully")

    async def is_duplicate(self, topic: str, event_id: str) -> bool:
        """
        Check apakah event sudah pernah diproses (duplicate).

        Args:
            topic: Topic event
            event_id: ID event

        Returns:
            True jika duplicate, False jika belum pernah diproses
        """
        async with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                "SELECT COUNT(*) FROM processed_events WHERE topic = ? AND event_id = ?",
                (topic, event_id),
            )
            count = cursor.fetchone()[0]
            conn.close()

            return count > 0

    async def mark_processed(
        self, topic: str, event_id: str, timestamp: str, source: str, payload: str
    ) -> bool:
        """
        Mark event sebagai sudah diproses.

        Args:
            topic: Topic event
            event_id: ID event
            timestamp: Timestamp event
            source: Source event
            payload: Payload event (JSON string)

        Returns:
            True jika berhasil disimpan (event baru),
            False jika sudah ada (duplicate)
        """
        async with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            try:
                processed_at = datetime.utcnow().isoformat()
                cursor.execute(
                    """
                    INSERT INTO processed_events
                    (topic, event_id, timestamp, source, payload, processed_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (topic, event_id, timestamp, source, payload, processed_at),
                )

                conn.commit()
                logger.info(
                    f"Event marked as processed: topic={topic}, event_id={event_id}"
                )
                return True

            except sqlite3.IntegrityError:
                logger.warning(
                    f"Duplicate event detected: topic={topic}, event_id={event_id}"
                )
                return False

            finally:
                conn.close()

    async def increment_received(self):
        """Increment counter untuk total event yang diterima."""
        async with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("UPDATE stats SET received = received + 1 WHERE id = 1")
            conn.commit()
            conn.close()

    async def increment_unique_processed(self):
        """Increment counter untuk event unik yang diproses."""
        async with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE stats SET unique_processed = unique_processed + 1 WHERE id = 1"
            )
            conn.commit()
            conn.close()

    async def increment_duplicate_dropped(self):
        """Increment counter untuk duplikat yang di-drop."""
        async with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE stats SET duplicate_dropped = duplicate_dropped + 1 WHERE id = 1"
            )
            conn.commit()
            conn.close()

    async def get_stats(self) -> Tuple[int, int, int]:
        """
        Get statistik sistem.

        Returns:
            Tuple (received, unique_processed, duplicate_dropped)
        """
        async with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT received, unique_processed, duplicate_dropped FROM stats WHERE id = 1"
            )
            result = cursor.fetchone()
            conn.close()

            if result:
                return result
            return (0, 0, 0)

    async def get_events(self, topic: Optional[str] = None) -> List[dict]:
        """
        Get list event yang sudah diproses.

        Args:
            topic: Filter berdasarkan topic (optional)

        Returns:
            List dictionary event
        """
        async with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            if topic:
                cursor.execute(
                    """
                    SELECT topic, event_id, timestamp, source, payload
                    FROM processed_events
                    WHERE topic = ?
                    ORDER BY processed_at DESC
                """,
                    (topic,),
                )
            else:
                cursor.execute("""
                    SELECT topic, event_id, timestamp, source, payload
                    FROM processed_events
                    ORDER BY processed_at DESC
                """)

            rows = cursor.fetchall()
            conn.close()

            events = []
            for row in rows:
                events.append(
                    {
                        "topic": row[0],
                        "event_id": row[1],
                        "timestamp": row[2],
                        "source": row[3],
                        "payload": row[4],
                    }
                )

            return events

    async def get_unique_topics_count(self) -> int:
        """
        Get jumlah topic unik.

        Returns:
            Jumlah topic unik
        """
        async with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(DISTINCT topic) FROM processed_events")
            count = cursor.fetchone()[0]
            conn.close()
            return count

    async def clear_all(self):
        """
        Clear semua data (untuk testing).
        """
        async with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM processed_events")
            cursor.execute(
                "UPDATE stats SET received = 0, unique_processed = 0, duplicate_dropped = 0 WHERE id = 1"
            )
            conn.commit()
            conn.close()
            logger.info("All data cleared from dedup store")

    def close(self):
        """
        Cleanup resources.
        """
        logger.info("DedupStore closed")
