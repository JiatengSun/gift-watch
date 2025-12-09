from __future__ import annotations

from typing import Any, Dict, Optional
import logging

from config.settings import Settings
from core.gift_parser import parse_send_gift, GiftEvent, SUPPORTED_GIFT_CMDS
from db.repo import insert_gift
from core.rule_engine import GiftRule
from core.rate_limiter import RateLimiter
from core.danmaku_sender import DanmakuSender

class IngestPipeline:
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

        if not self.rule.hit(gift):
            return

        # COMBO_SEND 会频繁触发多次事件，如果套用全局/用户冷却会导致只有第一条连击礼物被回复。
        # 对于连击，直接跳过冷却限制，保证每个连击包裹都能即时致谢。
        if cmd != "COMBO_SEND" and gift.uid and not self.limiter.allow(gift.uid, gift.ts):
            return

        await self.sender.send_thanks(gift.uname, gift.gift_name, gift.num)
