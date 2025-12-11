from __future__ import annotations

from typing import Any, DefaultDict, Dict, Optional
import logging
import asyncio
from collections import defaultdict
from dataclasses import dataclass, field

from config.settings import Settings
from core.gift_parser import parse_send_gift, GiftEvent, SUPPORTED_GIFT_CMDS
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
        self._count_day: str | None = None
        self._thanked_users: set[Any] = set()
        self._daily_counter = DailyGiftCounter()

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

        if not self.rule.is_target_gift(gift):
            return

        key = self._user_key(gift)
        day, total = self._daily_counter.add(key, gift.num or 1, gift.ts)
        self._reset_daily_thanks(day)

        if key in self._thanked_users:
            return

        if total < self.rule.min_num:
            return

        # COMBO_SEND 会频繁触发多次事件，如果套用全局/用户冷却会导致只有第一条连击礼物被回复。
        # 对于连击，直接跳过冷却限制，保证每个连击包裹都能被计入 5 秒内的结算。
        if cmd != "COMBO_SEND" and gift.uid and not self.limiter.allow(gift.uid, gift.ts):
            return

        self._thanked_users.add(key)
        self._buffer_thanks(gift)

    def _reset_daily_thanks(self, day: str) -> None:
        if self._count_day != day:
            self._count_day = day
            self._thanked_users = set()

    def _user_key(self, gift: GiftEvent) -> Any:
        return gift.uid or f"guest:{gift.uname}"

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
