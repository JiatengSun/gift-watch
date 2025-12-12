from __future__ import annotations

import sqlite3
from pathlib import Path

from config.settings import Settings


def _debug_log(message: str) -> None:
    print(f"[db.init_db] {message}")


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


def _ensure_gifts_room_id(conn: sqlite3.Connection) -> None:
    """Guarantee the gifts table has a room_id column by rebuilding if needed."""

    if not _table_exists(conn, "gifts"):
        return

    if "room_id" in _column_names(conn, "gifts"):
        return

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS _gifts_rebuild (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts INTEGER NOT NULL,
          room_id INTEGER NOT NULL,
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

    existing_cols = _column_names(conn, "gifts")
    transferable_cols = [
        col
        for col in existing_cols
        if col
        in {
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

    if transferable_cols:
        col_list = ", ".join(transferable_cols)
        insert_cols = f"{col_list}, room_id"
        select_cols = f"{col_list}, 0"
    else:
        insert_cols = "room_id"
        select_cols = "0"

    conn.execute(
        f"INSERT INTO _gifts_rebuild ({insert_cols}) SELECT {select_cols} FROM gifts"
    )
    conn.execute("DROP TABLE gifts")
    conn.execute("ALTER TABLE _gifts_rebuild RENAME TO gifts")


def _force_recreate_gifts(conn: sqlite3.Connection) -> None:
    """Drop and recreate gifts with room_id, copying compatible data when possible."""

    has_existing = _table_exists(conn, "gifts")
    if has_existing:
        conn.execute("ALTER TABLE gifts RENAME TO _gifts_rebuild_source")
        source_table = "_gifts_rebuild_source"
        existing_cols = _column_names(conn, source_table)
        transferable_cols = [
            col
            for col in existing_cols
            if col
            in {
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
    else:
        source_table = None
        transferable_cols = []

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gifts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts INTEGER NOT NULL,
          room_id INTEGER NOT NULL,
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

    if source_table and transferable_cols:
        col_list = ", ".join(transferable_cols)
        insert_cols = f"{col_list}, room_id"
        select_cols = f"{col_list}, 0"
        conn.execute(
            f"INSERT INTO gifts ({insert_cols}) "
            f"SELECT {select_cols} FROM {source_table}"
        )

    if source_table:
        conn.execute(f"DROP TABLE IF EXISTS {source_table}")


def _guarantee_gifts_room_id(conn: sqlite3.Connection) -> bool:
    """Attempt twice to ensure gifts has room_id, logging outcomes."""

    if not _table_exists(conn, "gifts"):
        _debug_log("gifts table does not exist; skipping room_id guarantee")
        return False

    for attempt in range(2):
        cols = _column_names(conn, "gifts")
        _debug_log(
            f"attempt {attempt + 1}: gifts columns before ensure -> {sorted(cols)}"
        )
        if "room_id" in cols:
            _debug_log("room_id already present; no rebuild needed")
            return True

        _ensure_gifts_room_id(conn)
        conn.commit()

    cols = _column_names(conn, "gifts")
    _debug_log(
        f"room_id still missing after ensure attempts, columns now -> {sorted(cols)}"
    )
    return "room_id" in cols


def init_db(settings: Settings) -> None:
    schema_path = Path(__file__).with_name("schema.sql")
    schema_sql = schema_path.read_text(encoding="utf-8")
    with get_conn(settings) as conn:
        # Migrate legacy gifts tables before applying the schema. Commit early so
        # a later schema failure doesn't roll back the column migration.
        _migrate_gifts_room_id(conn)
        _guarantee_gifts_room_id(conn)
        conn.commit()

        statements = [s.strip() for s in schema_sql.split(";") if s.strip()]
        for idx, stmt in enumerate(statements, start=1):
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError as exc:
                if "room_id" not in str(exc):
                    raise

                _debug_log(
                    f"schema statement {idx} failed with missing room_id: {stmt}"
                )
                _force_recreate_gifts(conn)
                conn.commit()

                try:
                    conn.execute(stmt)
                except sqlite3.OperationalError as retry_exc:
                    if "room_id" in str(retry_exc):
                        _debug_log(
                            f"retry for statement {idx} still failed; columns -> "
                            f"{sorted(_column_names(conn, 'gifts'))}"
                        )
                    raise
