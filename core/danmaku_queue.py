from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class QueueMessage:
    id: int
    message: str
    not_before: float


class DanmakuQueue:
    def __init__(self, db_path: str, interval_sec: int = 3) -> None:
        self.db_path = str(db_path)
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
            cur = conn.execute("SELECT COUNT(1) FROM danmaku_queue_meta")
            count = cur.fetchone()[0]
            if not count:
                conn.execute("INSERT INTO danmaku_queue_meta(id, last_sent_at) VALUES (1, 0)")

    def _compute_not_before(self, conn: sqlite3.Connection, earliest: float | None = None) -> float:
        now = time.time()
        base = now if earliest is None else max(now, earliest)
        pending = conn.execute(
            "SELECT MAX(not_before) FROM danmaku_queue WHERE status IN ('pending', 'sending')"
        ).fetchone()[0]
        if pending is not None:
            base = max(base, float(pending) + self.interval_sec)

        last_sent = conn.execute(
            "SELECT last_sent_at FROM danmaku_queue_meta WHERE id = 1"
        ).fetchone()[0]
        if last_sent:
            base = max(base, float(last_sent) + self.interval_sec)
        return base

    def enqueue(self, message: str) -> int:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            not_before = self._compute_not_before(conn)
            cur = conn.execute(
                "INSERT INTO danmaku_queue(message, status, not_before, created_at)"
                " VALUES (?, 'pending', ?, ?)",
                (message, not_before, time.time()),
            )
            conn.commit()
            return int(cur.lastrowid)

    def claim_next(self) -> Optional[QueueMessage]:
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT id, message, not_before FROM danmaku_queue"
                " WHERE status='pending' AND not_before <= ?"
                " ORDER BY not_before ASC, id ASC LIMIT 1",
                (now,),
            ).fetchone()
            if not row:
                conn.commit()
                return None
            conn.execute(
                "UPDATE danmaku_queue SET status='sending' WHERE id=?",
                (row["id"],),
            )
            conn.commit()
            return QueueMessage(id=int(row["id"]), message=str(row["message"]), not_before=float(row["not_before"]))

    def next_available_delay(self) -> Optional[float]:
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MIN(not_before) FROM danmaku_queue WHERE status='pending'"
            ).fetchone()
            if not row or row[0] is None:
                return None
            return max(0.0, float(row[0]) - now)

    def mark_sent(self, msg_id: int) -> None:
        ts = time.time()
        with self._connect() as conn:
            conn.execute(
                "UPDATE danmaku_queue SET status='sent', sent_at=? WHERE id=?",
                (ts, msg_id),
            )
            conn.execute(
                "UPDATE danmaku_queue_meta SET last_sent_at=? WHERE id=1",
                (ts,),
            )

    def reschedule(self, msg_id: int, *, error: str | None = None) -> None:
        ts = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            not_before = self._compute_not_before(conn, ts + self.interval_sec)
            conn.execute(
                "UPDATE danmaku_queue SET status='pending', not_before=?, last_error=? WHERE id=?",
                (not_before, error, msg_id),
            )
            conn.commit()

    def mark_failed(self, msg_id: int, error: str) -> None:
        ts = time.time()
        with self._connect() as conn:
            conn.execute(
                "UPDATE danmaku_queue SET status='failed', sent_at=?, last_error=? WHERE id=?",
                (ts, error, msg_id),
            )

