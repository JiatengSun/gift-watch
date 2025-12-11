from __future__ import annotations

from typing import List, Optional, Tuple

from config.settings import Settings
from core.gift_parser import GiftEvent, GUARD_LEVEL_NAMES
from db.sqlite import get_conn


def insert_gift(settings: Settings, gift: GiftEvent) -> None:
    with get_conn(settings) as conn:
        conn.execute(
            """
            INSERT INTO gifts(ts, room_id, uid, uname, gift_id, gift_name, num, total_price, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (gift.ts, gift.room_id, gift.uid, gift.uname, gift.gift_id, gift.gift_name, gift.num, gift.total_price, gift.raw_json),
        )


def _ts_scale_flags(conn) -> tuple[bool, bool]:
    cur = conn.execute("SELECT MIN(ts), MAX(ts) FROM gifts")
    row = cur.fetchone()
    if not row or row[0] is None or row[1] is None:
        return False, False

    min_ts, max_ts = int(row[0]), int(row[1])
    has_seconds = min_ts < 1_000_000_000_000
    has_millis = max_ts >= 1_000_000_000_000
    return has_seconds, has_millis


def _convert_input_ts(value: int | None, target_scale: int, input_is_ms: bool) -> int | None:
    if value is None:
        return None
    if input_is_ms and target_scale == 1:
        return value // 1000
    if (not input_is_ms) and target_scale == 1000:
        return value * 1000
    return value


def _append_ts_clauses(
    conn, clauses: list[str], params: list[object], start_ts: int | None, end_ts: int | None
) -> None:
    if start_ts is None and end_ts is None:
        return

    has_seconds, has_millis = _ts_scale_flags(conn)
    if not has_seconds and not has_millis:
        return

    input_is_ms = any((v or 0) >= 1_000_000_000_000 for v in (start_ts, end_ts))
    ts_clauses: list[str] = []

    def build(scale: int) -> None:
        scaled_start = _convert_input_ts(start_ts, scale, input_is_ms)
        scaled_end = _convert_input_ts(end_ts, scale, input_is_ms)
        if scaled_start is None and scaled_end is None:
            return
        parts = []
        if scaled_start is not None:
            parts.append("ts >= ?")
            params.append(scaled_start)
        if scaled_end is not None:
            parts.append("ts <= ?")
            params.append(scaled_end)
        if parts:
            ts_clauses.append("(" + " AND ".join(parts) + ")")

    if has_seconds:
        build(1)
    if has_millis:
        build(1000)

    if ts_clauses:
        clauses.append("(" + " OR ".join(ts_clauses) + ")")


def _guard_level_clause(guard_level: int | None) -> tuple[str, list[object]]:
    if guard_level is None:
        return "", []

    guard_name = GUARD_LEVEL_NAMES.get(guard_level)
    if not guard_name:
        return "", []

    return " AND gift_name = ?", [guard_name]


def query_gifts_by_uname(
    settings: Settings,
    uname: str,
    limit: int = 200,
    start_ts: int | None = None,
    end_ts: int | None = None,
    guard_level: int | None = None,
) -> List[Tuple]:
    with get_conn(settings) as conn:
        clauses: list[str] = ["room_id = ?", "uname = ?"]
        params: list[object] = [settings.room_id, uname]
        _append_ts_clauses(conn, clauses, params, start_ts, end_ts)

        guard_clause, guard_params = _guard_level_clause(guard_level)
        if guard_clause:
            clauses.append(guard_clause.removeprefix(" AND "))
            params.extend(guard_params)

        where = "WHERE " + " AND ".join(clauses)

        cur = conn.execute(
            f"""
            SELECT id, ts, uid, uname, gift_name, num, total_price
            FROM gifts
            {where}
            ORDER BY ts DESC
            LIMIT ?
            """,
            (*params, limit),
        )
        return cur.fetchall()


def query_gifts_by_uname_and_gift(
    settings: Settings,
    uname: str,
    gift_name: str,
    limit: int = 200,
    start_ts: int | None = None,
    end_ts: int | None = None,
    guard_level: int | None = None,
) -> List[Tuple]:
    with get_conn(settings) as conn:
        clauses: list[str] = ["room_id = ?", "uname = ?", "gift_name = ?"]
        params: list[object] = [settings.room_id, uname, gift_name]
        _append_ts_clauses(conn, clauses, params, start_ts, end_ts)

        guard_clause, guard_params = _guard_level_clause(guard_level)
        if guard_clause:
            clauses.append(guard_clause.removeprefix(" AND "))
            params.extend(guard_params)

        where = "WHERE " + " AND ".join(clauses)

        cur = conn.execute(
            f"""
            SELECT id, ts, uid, uname, gift_name, num, total_price
            FROM gifts
            {where}
            ORDER BY ts DESC
            LIMIT ?
            """,
            (*params, limit),
        )
        return cur.fetchall()


def query_recent_gifts(
    settings: Settings,
    limit: int = 200,
    start_ts: int | None = None,
    end_ts: int | None = None,
    uname: str | None = None,
    gift_name: str | None = None,
    guard_level: int | None = None,
) -> List[Tuple]:
    with get_conn(settings) as conn:
        clauses = ["room_id = ?"]
        params: list[object] = [settings.room_id]

        _append_ts_clauses(conn, clauses, params, start_ts, end_ts)
        if uname:
            clauses.append("uname = ?")
            params.append(uname)
        if gift_name:
            clauses.append("gift_name = ?")
            params.append(gift_name)

        guard_clause, guard_params = _guard_level_clause(guard_level)
        if guard_clause:
            clauses.append(guard_clause.removeprefix(" AND "))
            params.extend(guard_params)

        where = ""
        if clauses:
            where = "WHERE " + " AND ".join(clauses)

        cur = conn.execute(
            f"""
            SELECT id, ts, uid, uname, gift_name, num, total_price
            FROM gifts
            {where}
            ORDER BY ts DESC
            LIMIT ?
            """,
            (*params, limit),
        )
        return cur.fetchall()


def query_gift_by_id(settings: Settings, gift_id: int) -> Optional[Tuple]:
    with get_conn(settings) as conn:
        cur = conn.execute(
            """
            SELECT id, ts, uid, uname, gift_name, num, total_price
            FROM gifts
            WHERE id = ? AND room_id = ?
            LIMIT 1
            """,
            (gift_id, settings.room_id),
        )
        return cur.fetchone()


def delete_gift_by_id(settings: Settings, gift_id: int) -> bool:
    with get_conn(settings) as conn:
        cur = conn.execute(
            "DELETE FROM gifts WHERE id = ? AND room_id = ?", (gift_id, settings.room_id)
        )
        return cur.rowcount > 0


def query_flow_summary(settings: Settings, start_ts: int | None = None, end_ts: int | None = None) -> dict[str, int]:
    with get_conn(settings) as conn:
        clauses = ["room_id = ?"]
        params: list[object] = [
            GUARD_LEVEL_NAMES[3],
            GUARD_LEVEL_NAMES[2],
            GUARD_LEVEL_NAMES[1],
            settings.room_id,
        ]

        _append_ts_clauses(conn, clauses, params, start_ts, end_ts)

        where = ""
        if clauses:
            where = "WHERE " + " AND ".join(clauses)

        cur = conn.execute(
            f"""
            SELECT
              COUNT(*) as record_count,
              COALESCE(SUM(num), 0) as total_num,
              COALESCE(SUM(total_price), 0) as total_price,
              SUM(CASE WHEN gift_name = ? THEN 1 ELSE 0 END) as captain,
              SUM(CASE WHEN gift_name = ? THEN 1 ELSE 0 END) as admiral,
              SUM(CASE WHEN gift_name = ? THEN 1 ELSE 0 END) as governor
            FROM gifts
            {where}
            """,
            params,
        )
        row = cur.fetchone()

    return {
        "record_count": int(row[0] or 0),
        "total_num": int(row[1] or 0),
        "total_price": int(row[2] or 0),
        "guard": {
            "captain": int(row[3] or 0),
            "admiral": int(row[4] or 0),
            "governor": int(row[5] or 0),
        },
    }
