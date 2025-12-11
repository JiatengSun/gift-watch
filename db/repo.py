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
    params = [uname]
    where = "WHERE uname = ?"
    if start_ts is not None:
        where += " AND ts >= ?"
        params.append(start_ts)
    if end_ts is not None:
        where += " AND ts <= ?"
        params.append(end_ts)

    guard_clause, guard_params = _guard_level_clause(guard_level)
    where += guard_clause
    params.extend(guard_params)

    with get_conn(settings) as conn:
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
    params = [uname, gift_name]
    where = "WHERE uname = ? AND gift_name = ?"
    if start_ts is not None:
        where += " AND ts >= ?"
        params.append(start_ts)
    if end_ts is not None:
        where += " AND ts <= ?"
        params.append(end_ts)

    guard_clause, guard_params = _guard_level_clause(guard_level)
    where += guard_clause
    params.extend(guard_params)

    with get_conn(settings) as conn:
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
    clauses = []
    params: list[object] = []

    if start_ts is not None:
        clauses.append("ts >= ?")
        params.append(start_ts)
    if end_ts is not None:
        clauses.append("ts <= ?")
        params.append(end_ts)
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

    with get_conn(settings) as conn:
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
            WHERE id = ?
            LIMIT 1
            """,
            (gift_id,),
        )
        return cur.fetchone()


def delete_gift_by_id(settings: Settings, gift_id: int) -> bool:
    with get_conn(settings) as conn:
        cur = conn.execute("DELETE FROM gifts WHERE id = ?", (gift_id,))
        return cur.rowcount > 0


def query_flow_summary(settings: Settings, start_ts: int | None = None, end_ts: int | None = None) -> dict[str, int]:
    clauses = []
    params: list[object] = []

    if start_ts is not None:
        clauses.append("ts >= ?")
        params.append(start_ts)
    if end_ts is not None:
        clauses.append("ts <= ?")
        params.append(end_ts)

    where = ""
    if clauses:
        where = "WHERE " + " AND ".join(clauses)

    with get_conn(settings) as conn:
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
            (*params, GUARD_LEVEL_NAMES[3], GUARD_LEVEL_NAMES[2], GUARD_LEVEL_NAMES[1]),
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
