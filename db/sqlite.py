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
    if "room_id" in columns:
        return

    original_columns = columns
    try:
        conn.execute(
            "ALTER TABLE gifts ADD COLUMN room_id INTEGER NOT NULL DEFAULT 0"
        )
        columns = _column_names(conn, "gifts")
    except sqlite3.OperationalError:
        columns = original_columns

    if "room_id" in columns:
        return

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS _gifts_migrating (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts INTEGER NOT NULL,
          room_id INTEGER NOT NULL DEFAULT 0,
          uid INTEGER,
          uname TEXT,
          gift_id INTEGER,
          gift_name TEXT,
          num INTEGER DEFAULT 1,
          total_price INTEGER DEFAULT 0,
          raw_json TEXT
        )
        """
    )

    existing_cols = [
        col for col in columns if col in {
            "id",
            "ts",
            "uid",
            "uname",
            "gift_id",
            "gift_name",
            "num",
            "total_price",
            "raw_json",
        }
    ]
    col_list = ", ".join(existing_cols)
    placeholder_cols = f"{col_list}, 0" if col_list else "0"
    insert_cols = (
        f"{col_list}, room_id" if col_list else "room_id"
    )
    select_cols = placeholder_cols if col_list else "0"

    conn.execute(
        f"INSERT INTO _gifts_migrating ({insert_cols}) "
        f"SELECT {select_cols} FROM gifts"
    )
    conn.execute("DROP TABLE gifts")
    conn.execute("ALTER TABLE _gifts_migrating RENAME TO gifts")


def init_db(settings: Settings) -> None:
    schema_path = Path(__file__).with_name("schema.sql")
    schema_sql = schema_path.read_text(encoding="utf-8")
    with get_conn(settings) as conn:
        _migrate_gifts_room_id(conn)
        conn.executescript(schema_sql)
