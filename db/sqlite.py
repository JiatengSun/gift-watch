from __future__ import annotations

import sqlite3
from pathlib import Path

from config.settings import Settings


def get_conn(settings: Settings) -> sqlite3.Connection:
    return sqlite3.connect(settings.db_path)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cur.fetchone() is not None


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}


def _migrate_gifts_room_id(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "gifts"):
        return

    columns = _column_names(conn, "gifts")
    if "room_id" not in columns:
        conn.execute("ALTER TABLE gifts ADD COLUMN room_id INTEGER NOT NULL DEFAULT 0")


def init_db(settings: Settings) -> None:
    schema_path = Path(__file__).with_name("schema.sql")
    schema_sql = schema_path.read_text(encoding="utf-8")
    with get_conn(settings) as conn:
        _migrate_gifts_room_id(conn)
        conn.executescript(schema_sql)
