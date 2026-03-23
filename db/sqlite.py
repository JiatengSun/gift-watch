from __future__ import annotations

import sqlite3
from pathlib import Path

from config.settings import Settings
from db.event_storage import (
    build_danmaku_payload,
    build_gift_payload,
    compact_json_text,
)


def _debug_log(message: str) -> None:
    print(f"[db.init_db] {message}")


def _configure_conn(conn: sqlite3.Connection) -> sqlite3.Connection:
    # Improve concurrency when multiple processes share the same database.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def get_conn(settings: Settings) -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path, timeout=30, check_same_thread=False)
    return _configure_conn(conn)


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


def _ensure_queue_room_id(conn: sqlite3.Connection) -> None:
    """Ensure danmaku_queue has a room_id column, rebuilding if required."""

    if not _table_exists(conn, "danmaku_queue"):
        return

    cols = _column_names(conn, "danmaku_queue")
    if "room_id" in cols:
        return

    try:
        conn.execute("ALTER TABLE danmaku_queue ADD COLUMN room_id INTEGER NOT NULL DEFAULT 0")
        cols = _column_names(conn, "danmaku_queue")
    except sqlite3.OperationalError:
        cols = _column_names(conn, "danmaku_queue")

    if "room_id" in cols:
        return

    conn.execute("ALTER TABLE danmaku_queue RENAME TO _danmaku_queue_rebuild_source")
    existing_cols = _column_names(conn, "_danmaku_queue_rebuild_source")
    transferable_cols = [
        col
        for col in existing_cols
        if col
        in {
            "id",
            "message",
            "status",
            "not_before",
            "created_at",
            "sent_at",
            "last_error",
        }
    ]

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS danmaku_queue (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          room_id INTEGER NOT NULL,
          message TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending',
          not_before REAL NOT NULL,
          created_at REAL NOT NULL,
          sent_at REAL,
          last_error TEXT
        )
        """
    )

    if transferable_cols:
        col_list = ", ".join(transferable_cols)
        insert_cols = f"{col_list}, room_id"
        select_cols = f"{col_list}, 0"
        conn.execute(
            f"INSERT INTO danmaku_queue ({insert_cols}) "
            f"SELECT {select_cols} FROM _danmaku_queue_rebuild_source"
        )

    conn.execute("DROP TABLE IF EXISTS _danmaku_queue_rebuild_source")


def _ensure_queue_meta_room_id(conn: sqlite3.Connection) -> None:
    """Ensure danmaku_queue_meta carries room_id as primary key."""

    if not _table_exists(conn, "danmaku_queue_meta"):
        return

    cols = _column_names(conn, "danmaku_queue_meta")
    if "room_id" in cols:
        return

    last_sent_row = conn.execute(
        "SELECT last_sent_at FROM danmaku_queue_meta LIMIT 1"
    ).fetchone()
    last_sent_at = float(last_sent_row[0]) if last_sent_row and last_sent_row[0] else 0.0

    conn.execute("ALTER TABLE danmaku_queue_meta RENAME TO _danmaku_queue_meta_old")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS danmaku_queue_meta (
          room_id INTEGER PRIMARY KEY,
          last_sent_at REAL DEFAULT 0
        )
        """
    )
    conn.execute(
        "INSERT OR IGNORE INTO danmaku_queue_meta(room_id, last_sent_at) VALUES (?, ?)",
        (0, last_sent_at),
    )
    conn.execute("DROP TABLE IF EXISTS _danmaku_queue_meta_old")


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


def _ensure_app_meta(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_meta (
          key TEXT PRIMARY KEY,
          value TEXT
        )
        """
    )


def _get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM app_meta WHERE key = ?", (key,)).fetchone()
    if not row:
        return None
    return str(row[0]) if row[0] is not None else None


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO app_meta(key, value)
        VALUES(?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def _compact_gifts_payloads(conn: sqlite3.Connection, batch_size: int = 500) -> int:
    if not _table_exists(conn, "gifts") or "raw_json" not in _column_names(conn, "gifts"):
        return 0

    updated = 0
    last_id = 0
    while True:
        rows = conn.execute(
            """
            SELECT id, ts, room_id, uid, uname, gift_id, gift_name, num, total_price, raw_json
            FROM gifts
            WHERE id > ? AND raw_json IS NOT NULL AND raw_json != ''
            ORDER BY id ASC
            LIMIT ?
            """,
            (last_id, batch_size),
        ).fetchall()
        if not rows:
            break

        payload_updates: list[tuple[str, int]] = []
        for row in rows:
            last_id = int(row[0])
            compact_payload = build_gift_payload(
                ts=int(row[1] or 0),
                room_id=int(row[2] or 0),
                uid=row[3],
                uname=str(row[4] or ""),
                gift_id=row[5],
                gift_name=str(row[6] or ""),
                num=int(row[7] or 0),
                total_price=int(row[8] or 0),
            )
            next_payload = compact_json_text(row[9], compact_payload)
            if next_payload != row[9]:
                payload_updates.append((next_payload, int(row[0])))

        if payload_updates:
            conn.executemany("UPDATE gifts SET raw_json = ? WHERE id = ?", payload_updates)
            updated += len(payload_updates)
            conn.commit()

    return updated


def _compact_danmaku_payloads(conn: sqlite3.Connection, batch_size: int = 500) -> int:
    if not _table_exists(conn, "danmaku_events") or "raw_json" not in _column_names(conn, "danmaku_events"):
        return 0

    updated = 0
    last_id = 0
    while True:
        rows = conn.execute(
            """
            SELECT id, ts, room_id, uid, uname, content, raw_json
            FROM danmaku_events
            WHERE id > ? AND raw_json IS NOT NULL AND raw_json != ''
            ORDER BY id ASC
            LIMIT ?
            """,
            (last_id, batch_size),
        ).fetchall()
        if not rows:
            break

        payload_updates: list[tuple[str, int]] = []
        for row in rows:
            last_id = int(row[0])
            compact_payload = build_danmaku_payload(
                ts=int(row[1] or 0),
                room_id=int(row[2] or 0),
                uid=row[3],
                uname=str(row[4] or ""),
                content=str(row[5] or ""),
            )
            next_payload = compact_json_text(row[6], compact_payload)
            if next_payload != row[6]:
                payload_updates.append((next_payload, int(row[0])))

        if payload_updates:
            conn.executemany(
                "UPDATE danmaku_events SET raw_json = ? WHERE id = ?",
                payload_updates,
            )
            updated += len(payload_updates)
            conn.commit()

    return updated


def _compact_legacy_payloads(conn: sqlite3.Connection, settings: Settings) -> None:
    if not settings.compact_legacy_payloads_on_startup:
        return

    if settings.raw_event_storage_mode == "full":
        return

    _ensure_app_meta(conn)
    compaction_key = "payload_compaction_v1"
    if _get_meta(conn, compaction_key) == "done":
        return

    _debug_log("starting payload compaction for legacy gifts/danmaku rows")
    gifts_updated = _compact_gifts_payloads(conn)
    danmaku_updated = _compact_danmaku_payloads(conn)
    _set_meta(conn, compaction_key, "done")
    conn.commit()

    if gifts_updated or danmaku_updated:
        _debug_log(
            f"payload compaction updated gifts={gifts_updated} danmaku_events={danmaku_updated}; vacuuming database"
        )
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("VACUUM")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    else:
        _debug_log("payload compaction found no rows to rewrite")


def init_db(settings: Settings) -> None:
    schema_path = Path(__file__).with_name("schema.sql")
    schema_sql = schema_path.read_text(encoding="utf-8")
    with get_conn(settings) as conn:
        # Migrate legacy gifts tables before applying the schema. Commit early so
        # a later schema failure doesn't roll back the column migration.
        _migrate_gifts_room_id(conn)
        _guarantee_gifts_room_id(conn)
        _ensure_queue_room_id(conn)
        _ensure_queue_meta_room_id(conn)
        _ensure_app_meta(conn)
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
                _ensure_queue_room_id(conn)
                _ensure_queue_meta_room_id(conn)
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

        _compact_legacy_payloads(conn, settings)
