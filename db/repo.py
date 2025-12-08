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
            (gift.ts, gift.room_id, gift.uid, gift.uname, gift.gift_id, gift.gift_name, gift.num, gift.total_price, gift.raw_json)
        )

def query_gifts_by_uname(settings: Settings, uname: str, limit: int = 200) -> List[Tuple]:
    with get_conn(settings) as conn:
        cur = conn.execute(
            """
            SELECT ts, uid, uname, gift_name, num, total_price
            FROM gifts
            WHERE uname = ?
            ORDER BY ts DESC
            LIMIT ?
            """,
            (uname, limit)
        )
        return cur.fetchall()

def query_gifts_by_uname_and_gift(settings: Settings, uname: str, gift_name: str, limit: int = 200) -> List[Tuple]:
    with get_conn(settings) as conn:
        cur = conn.execute(
            """
            SELECT ts, uid, uname, gift_name, num, total_price
            FROM gifts
            WHERE uname = ? AND gift_name = ?
            ORDER BY ts DESC
            LIMIT ?
            """,
            (uname, gift_name, limit)
        )
        return cur.fetchall()

def query_recent_gifts(settings: Settings, limit: int = 200) -> List[Tuple]:
    with get_conn(settings) as conn:
        cur = conn.execute(
            """
            SELECT ts, uid, uname, gift_name, num, total_price
            FROM gifts
            ORDER BY ts DESC
            LIMIT ?
            """,
            (limit,)
        )
        return cur.fetchall()
