from __future__ import annotations

import json
import logging
import socket
import urllib.error
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
    except urllib.error.HTTPError as exc:  # pragma: no cover - network path
        if exc.code == 404:
            logger.info("礼物清单接口不存在(HTTP 404)，将尝试备用接口：%s", url)
        else:
            logger.warning("礼物清单接口请求失败(HTTP %s)：%s", exc.code, url)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("礼物清单接口 HTTP 错误详情", exc_info=exc)
        return None
    except urllib.error.URLError as exc:  # pragma: no cover - network path
        reason = getattr(exc, "reason", None)
        if isinstance(reason, socket.timeout):
            logger.warning("礼物清单接口请求超时：%s", url)
        else:
            logger.warning("礼物清单接口网络错误：%s reason=%s", url, reason)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("礼物清单接口网络错误详情", exc_info=exc)
        return None
    except json.JSONDecodeError as exc:  # pragma: no cover - network path
        logger.warning("礼物清单接口返回非 JSON 数据：%s", url)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("礼物清单 JSON 解析详情", exc_info=exc)
        return None
    except Exception as exc:  # pragma: no cover - network path
        logger.warning("礼物清单接口请求异常：%s type=%s", url, type(exc).__name__)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("礼物清单接口异常详情", exc_info=exc)
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
