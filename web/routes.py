from __future__ import annotations

from datetime import datetime, time, timedelta

from fastapi import APIRouter, Query

from config.settings import get_settings
from db.repo import query_gifts_by_uname, query_gifts_by_uname_and_gift, query_recent_gifts
from services.gift_list_service import fetch_room_gift_list

router = APIRouter()

def _default_start_ts(now: datetime) -> int:
    eight_am = datetime.combine(now.date(), time(8, 0))
    if eight_am > now:
        eight_am = eight_am - timedelta(days=1)
    return int(eight_am.timestamp())


@router.get("/api/search")
def search(
    uname: str = Query(..., description="用户名"),
    gift_name: str | None = Query(None, description="礼物名"),
    limit: int = Query(200, ge=1, le=1000),
    start_ts: int | None = Query(None, description="开始时间（Unix 秒）"),
):
    settings = get_settings()
    now = datetime.now()
    effective_start_ts = start_ts if start_ts is not None else _default_start_ts(now)
    end_ts = int(now.timestamp())

    if gift_name:
        rows = query_gifts_by_uname_and_gift(
            settings, uname=uname, gift_name=gift_name, limit=limit, start_ts=effective_start_ts, end_ts=end_ts
        )
    else:
        rows = query_gifts_by_uname(settings, uname=uname, limit=limit, start_ts=effective_start_ts, end_ts=end_ts)

    return [
        {
            "ts": r[0],
            "uid": r[1],
            "uname": r[2],
            "gift_name": r[3],
            "num": r[4],
            "total_price": r[5],
        }
        for r in rows
    ]


@router.get("/api/gifts")
def list_gifts(limit: int = Query(200, ge=1, le=1000)):
    settings = get_settings()
    rows = query_recent_gifts(settings, limit=limit)

    return [
        {
            "ts": r[0],
            "uid": r[1],
            "uname": r[2],
            "gift_name": r[3],
            "num": r[4],
            "total_price": r[5],
        }
        for r in rows
    ]


@router.get("/api/room_gift_list")
def room_gift_list():
    settings = get_settings()
    return fetch_room_gift_list(settings)

@router.get("/api/check")
def check(
    uname: str = Query(...),
    gift_name: str = Query(...),
):
    settings = get_settings()
    rows = query_gifts_by_uname_and_gift(settings, uname=uname, gift_name=gift_name, limit=1)
    if not rows:
        return {"found": False, "latest": None}

    r = rows[0]
    return {
        "found": True,
        "latest": {
            "ts": r[0],
            "uid": r[1],
            "uname": r[2],
            "gift_name": r[3],
            "num": r[4],
            "total_price": r[5],
        }
    }
