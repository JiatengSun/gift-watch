from __future__ import annotations

import json
import logging
import os
from typing import Dict

from config.settings import Settings
from services.gift_list_service import fetch_room_gift_list

logger = logging.getLogger(__name__)

GIFT_PRICE_ENV_KEY = "GIFT_PRICE_CACHE"


def _normalize_price(value) -> int:
    try:
        price_int = int(float(value))
        return max(price_int, 0)
    except Exception:
        return 0


def _build_cache_from_list(settings: Settings) -> tuple[Dict[int, int], Dict[str, int]]:
    gifts = fetch_room_gift_list(settings)
    by_id: Dict[int, int] = {}
    by_name: Dict[str, int] = {}
    for item in gifts:
        unit_price = _normalize_price(item.get("price"))
        if unit_price <= 0:
            continue

        gift_id = item.get("id")
        gift_name = (item.get("name") or "").strip()

        if gift_id is not None:
            try:
                by_id[int(gift_id)] = unit_price
            except Exception:
                pass
        if gift_name:
            by_name[gift_name] = unit_price

    return by_id, by_name


def ensure_gift_price_cache(settings: Settings) -> tuple[Dict[int, int], Dict[str, int]]:
    """Ensure gift price cache exists in the environment.

    Fetches the gift list once on startup to avoid repeated network calls during
    profit calculation. Prices are kept in raw金瓜子，换算人民币时用 1000:1。
    """

    raw_cache = os.getenv(GIFT_PRICE_ENV_KEY, "")
    if raw_cache:
        try:
            payload = json.loads(raw_cache)
            if isinstance(payload, dict):
                return (
                    {int(k): int(v) for k, v in (payload.get("by_id") or {}).items()},
                    {str(k): int(v) for k, v in (payload.get("by_name") or {}).items()},
                )
        except Exception:
            logger.debug("解析已有的礼物价格缓存失败，将重新拉取", exc_info=True)

    price_by_id, price_by_name = _build_cache_from_list(settings)
    if not price_by_id and not price_by_name:
        logger.warning("礼物列表为空，无法缓存礼物价格")
        return price_by_id, price_by_name

    try:
        os.environ[GIFT_PRICE_ENV_KEY] = json.dumps(
            {"by_id": price_by_id, "by_name": price_by_name}, ensure_ascii=False
        )
    except Exception:
        logger.debug("写入礼物价格缓存环境变量失败", exc_info=True)

    return price_by_id, price_by_name

