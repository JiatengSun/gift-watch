from __future__ import annotations

from datetime import datetime, time, timedelta

from fastapi import APIRouter, HTTPException, Query

from config.settings import get_settings
from db.repo import (
    delete_gift_by_id,
    query_gift_by_id,
    query_gifts_by_uname,
    query_gifts_by_uname_and_gift,
    query_recent_gifts,
)
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
            "id": r[0],
            "ts": r[1],
            "uid": r[2],
            "uname": r[3],
            "gift_name": r[4],
            "num": r[5],
            "total_price": r[6],
        }
        for r in rows
    ]


@router.get("/api/gifts")
def list_gifts(limit: int = Query(200, ge=1, le=1000)):
    settings = get_settings()
    rows = query_recent_gifts(settings, limit=limit)

    return [
        {
            "id": r[0],
            "ts": r[1],
            "uid": r[2],
            "uname": r[3],
            "gift_name": r[4],
            "num": r[5],
            "total_price": r[6],
        }
        for r in rows
    ]


@router.get("/api/gifts/{gift_id}")
def get_gift(gift_id: int):
    settings = get_settings()
    row = query_gift_by_id(settings, gift_id)
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")

    return {
        "id": row[0],
        "ts": row[1],
        "uid": row[2],
        "uname": row[3],
        "gift_name": row[4],
        "num": row[5],
        "total_price": row[6],
    }


@router.delete("/api/gifts/{gift_id}")
def delete_gift(gift_id: int):
    settings = get_settings()
    deleted = delete_gift_by_id(settings, gift_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="记录不存在或已删除")
    return {"deleted": True, "id": gift_id}


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
            "id": r[0],
            "ts": r[1],
            "uid": r[2],
            "uname": r[3],
            "gift_name": r[4],
            "num": r[5],
            "total_price": r[6],
        },
    }
