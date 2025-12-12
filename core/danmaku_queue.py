from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class QueueMessage:
    id: int
    room_id: int
    message: str
    not_before: float


class DanmakuQueue:
    def __init__(self, db_path: str, room_id: int, interval_sec: int = 3) -> None:
        self.db_path = str(db_path)
        self.room_id = int(room_id)
        self.interval_sec = max(1, interval_sec)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        schema_path = Path(__file__).with_name("queue_schema.sql")
        schema_sql = schema_path.read_text(encoding="utf-8")
        with self._connect() as conn:
            conn.executescript(schema_sql)
            self._migrate_queue_room(conn)
            self._migrate_meta_table(conn)
            self._ensure_indexes(conn)
            self._ensure_meta_row(conn)

    def _migrate_queue_room(self, conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(danmaku_queue)")}
        if "room_id" not in columns:
            conn.execute(
                f"ALTER TABLE danmaku_queue ADD COLUMN room_id INTEGER NOT NULL DEFAULT {self.room_id}"
            )
            conn.execute(
                "UPDATE danmaku_queue SET room_id=? WHERE room_id IS NULL", (self.room_id,)
            )

    def _migrate_meta_table(self, conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(danmaku_queue_meta)")}
        if "room_id" in columns:
            return

        last_sent_row = conn.execute("SELECT last_sent_at FROM danmaku_queue_meta LIMIT 1").fetchone()
        last_sent_at = float(last_sent_row[0]) if last_sent_row and last_sent_row[0] else 0.0
        conn.execute("ALTER TABLE danmaku_queue_meta RENAME TO danmaku_queue_meta_old")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS danmaku_queue_meta ("
            "  room_id INTEGER PRIMARY KEY,"
            "  last_sent_at REAL DEFAULT 0"
            ")"
        )
        conn.execute(
            "INSERT OR IGNORE INTO danmaku_queue_meta(room_id, last_sent_at) VALUES (?, ?)",
            (self.room_id, last_sent_at),
        )
        conn.execute("DROP TABLE IF EXISTS danmaku_queue_meta_old")

    def _ensure_indexes(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_danmaku_queue_room_status_not_before "
            "ON danmaku_queue(room_id, status, not_before)"
        )

    def _ensure_meta_row(self, conn: sqlite3.Connection) -> None:
        cur = conn.execute(
            "SELECT COUNT(1) FROM danmaku_queue_meta WHERE room_id=?", (self.room_id,)
        )
        count = cur.fetchone()[0]
        if not count:
            conn.execute(
                "INSERT INTO danmaku_queue_meta(room_id, last_sent_at) VALUES (?, 0)",
                (self.room_id,),
            )

    def _compute_not_before(self, conn: sqlite3.Connection, earliest: float | None = None) -> float:
        now = time.time()
        base = now if earliest is None else max(now, earliest)
        pending = conn.execute(
            "SELECT MAX(not_before) FROM danmaku_queue"
            " WHERE status IN ('pending', 'sending') AND room_id=?",
            (self.room_id,),
        ).fetchone()[0]
        if pending is not None:
            base = max(base, float(pending) + self.interval_sec)

        last_sent = conn.execute(
            "SELECT last_sent_at FROM danmaku_queue_meta WHERE room_id = ?", (self.room_id,)
        ).fetchone()[0]
        if last_sent:
            base = max(base, float(last_sent) + self.interval_sec)
        return base

    def enqueue(self, message: str) -> int:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            not_before = self._compute_not_before(conn)
            cur = conn.execute(
                "INSERT INTO danmaku_queue(room_id, message, status, not_before, created_at)"
                " VALUES (?, ?, 'pending', ?, ?)",
                (self.room_id, message, not_before, time.time()),
            )
            conn.commit()
            return int(cur.lastrowid)

    def claim_next(self) -> Optional[QueueMessage]:
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT id, room_id, message, not_before FROM danmaku_queue"
                " WHERE status='pending' AND room_id=? AND not_before <= ?"
                " ORDER BY not_before ASC, id ASC LIMIT 1",
                (self.room_id, now),
            ).fetchone()
            if not row:
                conn.commit()
                return None
            conn.execute(
                "UPDATE danmaku_queue SET status='sending' WHERE id=? AND room_id=?",
                (row["id"], self.room_id),
            )
            conn.commit()
            return QueueMessage(
                id=int(row["id"]),
                room_id=int(row["room_id"]),
                message=str(row["message"]),
                not_before=float(row["not_before"]),
            )

    def next_available_delay(self) -> Optional[float]:
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MIN(not_before) FROM danmaku_queue WHERE status='pending' AND room_id=?",
                (self.room_id,),
            ).fetchone()
            if not row or row[0] is None:
                return None
            return max(0.0, float(row[0]) - now)

    def mark_sent(self, msg_id: int) -> None:
        ts = time.time()
        with self._connect() as conn:
            conn.execute(
                "UPDATE danmaku_queue SET status='sent', sent_at=? WHERE id=? AND room_id=?",
                (ts, msg_id, self.room_id),
            )
            conn.execute(
                "UPDATE danmaku_queue_meta SET last_sent_at=? WHERE room_id=?",
                (ts, self.room_id),
            )

    def reschedule(self, msg_id: int, *, error: str | None = None) -> None:
        ts = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            not_before = self._compute_not_before(conn, ts + self.interval_sec)
            conn.execute(
                "UPDATE danmaku_queue SET status='pending', not_before=?, last_error=?"
                " WHERE id=? AND room_id=?",
                (not_before, error, msg_id, self.room_id),
            )
            conn.commit()

    def mark_failed(self, msg_id: int, error: str) -> None:
        ts = time.time()
        with self._connect() as conn:
            conn.execute(
                "UPDATE danmaku_queue SET status='failed', sent_at=?, last_error=?"
                " WHERE id=? AND room_id=?",
                (ts, error, msg_id, self.room_id),
            )

