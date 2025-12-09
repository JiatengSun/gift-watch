from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any, Dict, List

from config.settings import Settings

logger = logging.getLogger(__name__)


def fetch_room_gift_list(settings: Settings) -> List[Dict[str, Any]]:
    """Fetch the gift list for the configured room.

    Returns a simplified schema suitable for the frontend.
    """

    url = (
        "https://api.live.bilibili.com/xlive/web-room/v1/giftPanel/giftList"
        f"?roomid={settings.room_id}&platform=pc&source=live"
    )

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/117.0",
                "Referer": f"https://live.bilibili.com/{settings.room_id}",
                "Origin": "https://live.bilibili.com",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
        payload = json.loads(raw)
    except Exception as exc:  # pragma: no cover - network path
        logger.warning("获取礼物清单失败", exc_info=exc)
        return []

    if payload.get("code") != 0:
        logger.warning("礼物清单接口返回异常：%s", payload)
        return []

    gifts = []
    data = payload.get("data") or {}
    for item in data.get("list", []):
        gifts.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "price": item.get("price"),
                "coin_type": item.get("coin_type"),
                "corner_mark": item.get("corner_mark"),
                "gift_type": item.get("gift_type"),
            }
        )

    return gifts
