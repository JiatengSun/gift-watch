from __future__ import annotations

from config.settings import Settings
from core.bili_client import get_bot_credential
from core.rule_engine import build_rule
from core.rate_limiter import RateLimiter
from core.danmaku_sender import DanmakuSender
from services.ingest_pipeline import IngestPipeline

def build_pipeline(settings: Settings) -> IngestPipeline:
    rule = build_rule(
        settings.target_gifts, settings.target_gift_ids, settings.target_min_num
    )
    limiter = RateLimiter(
        global_cooldown_sec=settings.thank_global_cooldown_sec,
        per_user_cooldown_sec=settings.thank_per_user_cooldown_sec,
        per_user_daily_limit=settings.thank_per_user_daily_limit,
    )

    sender = None
    if settings.bot_sessdata and settings.bot_bili_jct:
        credential = get_bot_credential(settings)
        sender = DanmakuSender(
            settings.room_id,
            credential,
            thank_message_single=settings.thank_message_single,
            thank_message_summary=settings.thank_message_summary,
            thank_message_guard=settings.thank_message_guard,
        )

    return IngestPipeline(settings=settings, rule=rule, limiter=limiter, sender=sender)
