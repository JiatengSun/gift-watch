from __future__ import annotations

from typing import Any, Dict, Optional

from config.settings import Settings
from core.gift_parser import parse_send_gift, GiftEvent
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

    async def handle_event(self, event: Dict[str, Any]) -> None:
        gift = parse_send_gift(event, room_id=self.settings.room_id)
        if gift is None:
            return

        insert_gift(self.settings, gift)

        if self.sender is None:
            return

        if not self.rule.hit(gift):
            return

        if gift.uid and not self.limiter.allow(gift.uid, gift.ts):
            return

        await self.sender.send_thanks(gift.uname, gift.gift_name, gift.num)
