from __future__ import annotations

from typing import Any, DefaultDict, Dict, Optional
import logging
import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field

from config.settings import Settings
from core.gift_parser import (
    GiftEvent,
    GUARD_LEVEL_NAMES,
    SUPPORTED_GIFT_CMDS,
    parse_guard_buy,
    parse_send_gift,
)
from db.repo import insert_gift
from core.rule_engine import DailyGiftCounter, GiftRule
from core.rate_limiter import RateLimiter
from core.danmaku_sender import DanmakuSender


@dataclass
class PendingThanks:
    uname: str
    gifts: DefaultDict[str, int] = field(default_factory=lambda: defaultdict(int))
    task: Optional[asyncio.Task] = None

class IngestPipeline:
    THANK_DELAY_SECONDS = 5

    def __init__(
        self,
        settings: Settings,
        rule: GiftRule,
        limiter: RateLimiter,
        sender: Optional[DanmakuSender] = None,
    ):
        self.settings = settings
        self.rule = rule
        self.limiter = limiter
        self.sender = sender
        self.logger = logging.getLogger(__name__)
        self._pending_thanks: Dict[Any, PendingThanks] = {}
        self._thanks_day: str | None = None
        self._threshold_hits: Dict[Any, int] = {}
        self._daily_counter = DailyGiftCounter()
        self._user_day_thanks: Dict[Any, int] = {}

    async def handle_event(self, event: Dict[str, Any]) -> None:
        # AsyncEvent 会在触发任意事件时再派发一次 __ALL__，形式为
        # {"name": "<cmd>", "data": (<event>,)}，这里兼容这种结构。
        if isinstance(event, dict) and "name" in event and "data" in event:
            data = event.get("data")
            if isinstance(data, (list, tuple)) and data and isinstance(data[0], dict):
                inner_event = dict(data[0])
                if "cmd" not in inner_event and event.get("name"):
                    inner_event["cmd"] = event["name"]
                event = inner_event

        cmd = event.get("cmd") or event.get("command") or event.get("type")
        if cmd and "cmd" not in event:
            event["cmd"] = cmd
        if cmd and cmd not in SUPPORTED_GIFT_CMDS:
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug("忽略非礼物事件 cmd=%s keys=%s", cmd, list(event.keys()))
            return
        if cmd and self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug("收到事件 cmd=%s keys=%s", cmd, list(event.keys()))
        gift: Optional[GiftEvent]
        if cmd == "GUARD_BUY":
            gift = parse_guard_buy(event, room_id=self.settings.room_id)
        else:
            gift = parse_send_gift(event, room_id=self.settings.room_id)
        if gift is None:
            if cmd == "SEND_GIFT":
                self.logger.warning("收到 SEND_GIFT 但无法解析，原始事件: %s", event)
            return

        insert_gift(self.settings, gift)

        self.logger.info(
            "📦 收到礼物：uid=%s uname=%s gift=%s x%d price=%s",
            gift.uid,
            gift.uname,
            gift.gift_name,
            gift.num,
            gift.total_price,
        )

        if self.sender is None:
            return

        if cmd == "GUARD_BUY" and self.settings.thank_guard:
            guard_name = GUARD_LEVEL_NAMES.get(gift.gift_id, GUARD_LEVEL_NAMES[3])
            await self.sender.send_guard_thanks(gift.uname, guard_name)

        key = self._user_key(gift)
        day_key = self._ensure_thanks_day(gift.ts)

        if self.settings.thank_mode == "value":
            if not self._should_thank_by_value(gift):
                return
            if not self._allow_thanks(key, gift.ts, ignore_cooldown=cmd == "COMBO_SEND"):
                return
            self._buffer_thanks(gift)
            return

        if not self._is_target_gift(gift):
            return

        day, total = self._daily_counter.add(key, gift.num or 1, gift.ts)
        if day != day_key:
            self._ensure_thanks_day(gift.ts)

        threshold = max(self.rule.min_num, 1)
        reached = total // threshold
        sent = self._threshold_hits.get(key, 0)
        if reached <= sent:
            return

        if not self._allow_thanks(key, gift.ts, ignore_cooldown=cmd == "COMBO_SEND"):
            return

        self._threshold_hits[key] = reached
        self._buffer_thanks(gift)

    def _user_key(self, gift: GiftEvent) -> Any:
        return gift.uid or f"guest:{gift.uname}"

    def _ensure_thanks_day(self, ts: float) -> str:
        day = time.strftime("%Y-%m-%d", time.localtime(ts))
        if self._thanks_day != day:
            self._thanks_day = day
            self._threshold_hits = {}
            self._user_day_thanks = {}
        return day

    def _allow_thanks(self, key: Any, ts: float, *, ignore_cooldown: bool = False) -> bool:
        daily_sent = self._user_day_thanks.get(key, 0)
        if self.settings.thank_per_user_daily_limit > 0 and daily_sent >= self.settings.thank_per_user_daily_limit:
            return False

        allowed = self.limiter.allow(key, ts, ignore_cooldown=ignore_cooldown)
        if allowed:
            self._user_day_thanks[key] = daily_sent + 1
        return allowed

    def _is_target_gift(self, gift: GiftEvent) -> bool:
        if self.settings.thank_mode == "value" and not self.rule.target_gift_ids and not self.rule.target_gift_names:
            return True
        return self.rule.is_target_gift(gift)

    def _should_thank_by_value(self, gift: GiftEvent) -> bool:
        if self.settings.thank_value_threshold <= 0:
            return False
        if not self._is_target_gift(gift):
            return False
        return gift.total_price >= self.settings.thank_value_threshold

    def _buffer_thanks(self, gift: GiftEvent) -> None:
        """将同一用户 5 秒内的礼物合并，再发送一条汇总感谢，避免刷屏。"""

        if self.sender is None:
            return

        key = gift.uid or f"guest:{gift.uname}"
        pending = self._pending_thanks.get(key)
        if pending is None:
            pending = PendingThanks(uname=gift.uname)
            self._pending_thanks[key] = pending
            pending.task = asyncio.create_task(self._flush_thanks_after_delay(key))

        pending.uname = gift.uname  # 更新昵称，避免用户改名导致的旧称呼
        pending.gifts[gift.gift_name] += gift.num or 1

    async def _flush_thanks_after_delay(self, key: Any) -> None:
        try:
            await asyncio.sleep(self.THANK_DELAY_SECONDS)
            pending = self._pending_thanks.pop(key, None)
            if pending and pending.gifts and self.sender:
                await self.sender.send_summary_thanks(pending.uname, dict(pending.gifts))
        except Exception:
            self.logger.exception("发送汇总感谢消息失败")
