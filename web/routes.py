from __future__ import annotations

from fastapi import APIRouter, Query

from config.settings import get_settings
from db.repo import query_gifts_by_uname, query_gifts_by_uname_and_gift

router = APIRouter()

@router.get("/api/search")
def search(
    uname: str = Query(..., description="用户名"),
    gift_name: str | None = Query(None, description="礼物名"),
    limit: int = Query(200, ge=1, le=1000),
):
    settings = get_settings()

    if gift_name:
        rows = query_gifts_by_uname_and_gift(settings, uname=uname, gift_name=gift_name, limit=limit)
    else:
        rows = query_gifts_by_uname(settings, uname=uname, limit=limit)

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
