from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
import time
import json

@dataclass
class GiftEvent:
    ts: int
    room_id: int
    uid: int
    uname: str
    gift_id: int
    gift_name: str
    num: int
    total_price: int
    raw_json: str

def parse_send_gift(event: Dict[str, Any], room_id: int) -> Optional[GiftEvent]:
    # 兼容不同封装形态
    cmd = event.get("cmd") or event.get("command")
    if cmd != "SEND_GIFT":
        return None

    data = event.get("data") or {}
    try:
        uid = int(data.get("uid") or 0)
    except Exception:
        uid = 0
    uname = str(data.get("uname") or "")

    gift_name = str(data.get("giftName") or data.get("gift_name") or "")
    try:
        gift_id = int(data.get("giftId") or data.get("gift_id") or 0)
    except Exception:
        gift_id = 0

    try:
        num = int(data.get("num") or 1)
    except Exception:
        num = 1

    # 价格字段在不同事件里有差异，这里尽量容错
    total_price = 0
    for k in ("total_coin", "totalCoin", "price", "giftPrice"):
        v = data.get(k)
        if v is None:
            continue
        try:
            total_price = int(v)
            break
        except Exception:
            continue

    ts = int(data.get("timestamp") or event.get("timestamp") or time.time())

    raw_json = json.dumps(event, ensure_ascii=False)

    if not uname or not gift_name:
        return None

    return GiftEvent(
        ts=ts,
        room_id=room_id,
        uid=uid,
        uname=uname,
        gift_id=gift_id,
        gift_name=gift_name,
        num=num,
        total_price=total_price,
        raw_json=raw_json
    )
