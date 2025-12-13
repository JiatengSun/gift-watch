from __future__ import annotations

import json
import logging
import socket
import urllib.request
from typing import Any, Dict, List

from config.settings import Settings

logger = logging.getLogger(__name__)


def _fetch_payload(
    url: str, headers: Dict[str, str], *, timeout: float | None = 3.0
) -> Dict[str, Any] | None:
    """Attempt to fetch and decode the gift payload from the given URL."""

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
        return json.loads(raw)
    except Exception as exc:  # pragma: no cover - network path
        reason = getattr(exc, "reason", None)
        is_timeout = isinstance(reason, socket.timeout)
        log_suffix = "(超时)" if is_timeout else ""
        logger.warning("获取礼物清单失败%s：%s", log_suffix, url, exc_info=exc)
        return None


def fetch_room_gift_list(
    settings: Settings, *, timeout: float | None = 3.0
) -> List[Dict[str, Any]]:
    """Fetch the gift list for the configured room.

    Returns a simplified schema suitable for the frontend. Tries the primary
    giftList endpoint first and falls back to giftConfig if the former returns
    an error such as HTTP 404.
    """

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/117.0",
        "Referer": f"https://live.bilibili.com/{settings.room_id}",
        "Origin": "https://live.bilibili.com",
    }

    candidate_urls = [
        "https://api.live.bilibili.com/xlive/web-room/v1/giftPanel/giftList"
        f"?roomid={settings.room_id}&platform=pc&source=live",
        "https://api.live.bilibili.com/xlive/web-room/v1/giftPanel/giftConfig"
        f"?roomid={settings.room_id}&platform=pc&source=live",
    ]

    payload = None
    for url in candidate_urls:
        payload = _fetch_payload(url, headers, timeout=timeout)
        if payload and payload.get("code") == 0:
            break

    if not payload or payload.get("code") != 0:
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
