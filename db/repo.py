from __future__ import annotations

from typing import List, Optional, Tuple

from config.settings import Settings
from core.gift_parser import GiftEvent
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


def query_gifts_by_uname(
    settings: Settings, uname: str, limit: int = 200, start_ts: int | None = None, end_ts: int | None = None
) -> List[Tuple]:
    params = [uname]
    where = "WHERE uname = ?"
    if start_ts is not None:
        where += " AND ts >= ?"
        params.append(start_ts)
    if end_ts is not None:
        where += " AND ts <= ?"
        params.append(end_ts)

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
) -> List[Tuple]:
    params = [uname, gift_name]
    where = "WHERE uname = ? AND gift_name = ?"
    if start_ts is not None:
        where += " AND ts >= ?"
        params.append(start_ts)
    if end_ts is not None:
        where += " AND ts <= ?"
        params.append(end_ts)

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


def query_recent_gifts(settings: Settings, limit: int = 200) -> List[Tuple]:
    with get_conn(settings) as conn:
        cur = conn.execute(
            """
            SELECT id, ts, uid, uname, gift_name, num, total_price
            FROM gifts
            ORDER BY ts DESC
            LIMIT ?
            """,
            (limit,),
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
