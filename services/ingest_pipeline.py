from __future__ import annotations

from typing import Any, DefaultDict, Dict, Optional
import logging
import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field

from config.settings import Settings, SettingsReloader
from core.gift_parser import (
    GiftEvent,
    GUARD_LEVEL_NAMES,
    SUPPORTED_GIFT_CMDS,
    parse_guard_buy,
    parse_send_gift,
)
from db.repo import insert_gift, query_blind_box_totals
from core.rule_engine import DailyGiftCounter, GiftRule, build_rule
from core.rate_limiter import RateLimiter
from core.danmaku_sender import DanmakuSender
from core.bili_client import get_bot_credential


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
        settings_reloader: Optional[SettingsReloader] = None,
    ):
        self.settings = settings
        self.rule = rule
        self.limiter = limiter
        self.sender = sender
        self.settings_reloader = settings_reloader
        self.logger = logging.getLogger(__name__)
        self._pending_thanks: Dict[Any, PendingThanks] = {}
        self._thanks_day: str | None = None
        self._threshold_hits: Dict[Any, int] = {}
        self._daily_counter = DailyGiftCounter()
        self._user_day_thanks: Dict[Any, int] = {}
        self._blind_box_cooldown: Dict[Any, float] = {}

    def _coerce_event_object(self, event: Any) -> dict[str, Any] | None:
        """Convert bilibili-api event objects into plain dictionaries.

        Recent bilibili-api versions wrap danmaku/gift messages in typed objects
        instead of dicts. Accessing attributes like ``event.get`` on those
        objects would raise ``AttributeError`` and break the ingest loop.
        """

        if isinstance(event, dict):
            return event

        if hasattr(event, "__dict__"):
            coerced = dict(vars(event))
            for key in ("data", "info"):
                inner = getattr(event, key, None)
                if isinstance(inner, dict):
                    coerced.setdefault(key, inner)
            # Some bilibili-api objects expose the command name via ``cmd`` or
            # ``command`` attributes; copying __dict__ above will already catch
            # them when present.
            return coerced

        return None

    def _refresh_sender(self) -> None:
        if not self.settings.bot_sessdata or not self.settings.bot_bili_jct:
            self.sender = None
            return

        credential = get_bot_credential(self.settings)
        if self.sender is None:
            self.sender = DanmakuSender(
                self.settings.room_id,
                credential,
                thank_message_single=self.settings.thank_message_single,
                thank_message_summary=self.settings.thank_message_summary,
                thank_message_guard=self.settings.thank_message_guard,
                max_length=self.settings.danmaku_max_length,
                queue_db_path=self.settings.danmaku_queue_db_path if self.settings.danmaku_queue_enabled else None,
                queue_interval_sec=self.settings.danmaku_queue_interval_sec,
            )
            return

        self.sender.reconfigure(
            room_id=self.settings.room_id,
            credential=credential,
            thank_message_single=self.settings.thank_message_single,
            thank_message_summary=self.settings.thank_message_summary,
            thank_message_guard=self.settings.thank_message_guard,
            max_length=self.settings.danmaku_max_length,
            queue_db_path=self.settings.danmaku_queue_db_path if self.settings.danmaku_queue_enabled else None,
            queue_interval_sec=self.settings.danmaku_queue_interval_sec,
        )

    def _refresh_settings(self) -> None:
        if self.settings_reloader is None:
            return

        latest = self.settings_reloader.reload_if_changed()
        if latest == self.settings:
            return

        self.logger.info("检测到配置更新，重新加载感谢规则和限流")
        self.settings = latest
        self.rule = build_rule(
            self.settings.target_gifts, self.settings.target_gift_ids, self.settings.target_min_num
        )
        self.limiter = RateLimiter(
            global_cooldown_sec=self.settings.thank_global_cooldown_sec,
            per_user_cooldown_sec=self.settings.thank_per_user_cooldown_sec,
            per_user_daily_limit=self.settings.thank_per_user_daily_limit,
        )
        self._pending_thanks = {}
        self._threshold_hits = {}
        self._daily_counter = DailyGiftCounter()
        self._user_day_thanks = {}
        self._thanks_day = None
        self._blind_box_cooldown = {}
        self._refresh_sender()

    async def handle_event(self, event: Dict[str, Any]) -> None:
        self._refresh_settings()
        coerced_event = self._coerce_event_object(event)
        if coerced_event is None:
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug(
                    "忽略无法解析的事件类型 type=%s", type(event).__name__
                )
            return
        event = coerced_event
        # AsyncEvent 会在触发任意事件时再派发一次 __ALL__，形式为
        # {"name": "<cmd>", "data": (<event>,)}，这里兼容这种结构。
        if isinstance(event, dict) and "name" in event and "data" in event:
            data = event.get("data")
            if isinstance(data, (list, tuple)) and data and isinstance(data[0], dict):
                inner_event = dict(data[0])
            elif isinstance(data, dict):
                inner_event = dict(data)
            else:
                inner_event = None

            if inner_event is not None:
                if "cmd" not in inner_event and event.get("name"):
                    inner_event["cmd"] = event["name"]
                event = inner_event

        cmd = event.get("cmd") or event.get("command") or event.get("type")
        if cmd and "cmd" not in event:
            event["cmd"] = cmd

        coerced_data = self._coerce_event_data(event)
        if coerced_data is not None and coerced_data is not event.get("data"):
            event = dict(event)
            event["data"] = coerced_data
            # 可能在 data 中携带更准确的命令
            if not cmd:
                cmd = event.get("cmd") or event.get("command") or event.get("type")

        if self._is_danmaku_event(event, cmd):
            await self._handle_blind_box_query(event)
            return

        gift_like = self._is_gift_like_event(event)
        if cmd and cmd not in SUPPORTED_GIFT_CMDS and not gift_like:
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug("忽略非礼物事件 cmd=%s keys=%s", cmd, list(event.keys()))
            return

        if cmd in SUPPORTED_GIFT_CMDS and not gift_like:
            data = event.get("data")
            if not isinstance(data, dict):
                if self.logger.isEnabledFor(logging.DEBUG):
                    self.logger.debug(
                        "忽略缺少礼物字段的事件 cmd=%s data_type=%s keys=%s",
                        cmd,
                        type(data).__name__,
                        list(event.keys()),
                    )
                return

        if cmd and self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug("收到事件 cmd=%s keys=%s", cmd, list(event.keys()))
        gift: Optional[GiftEvent]
        if cmd == "GUARD_BUY":
            gift = parse_guard_buy(event, room_id=self.settings.room_id)
        else:
            gift = parse_send_gift(
                event, room_id=self.settings.room_id, allow_unknown_cmd=gift_like
            )
        if gift is None:
            if cmd == "SEND_GIFT":
                self.logger.warning("收到 SEND_GIFT 但无法解析，原始事件: %s", event)
            elif gift_like:
                self.logger.debug("检测到礼物字段但解析失败 cmd=%s event=%s", cmd, event)
            return

        self._apply_gift_price(gift)

        blind_box_base = self.settings.blind_box_base_gift.strip()
        if blind_box_base and gift.gift_name.strip() == blind_box_base:
            self.logger.debug("跳过盲盒基础礼物入库 gift=%s", gift.gift_name)
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

    def _parse_danmaku_event(self, event: dict[str, Any]) -> tuple[int | None, str, str] | None:
        data = event
        if isinstance(event.get("data"), dict):
            data = event.get("data") or {}

        info = data.get("info") or event.get("info")
        if isinstance(info, dict):  # 某些封装会把 info 放到 data.data 下
            info = info.get("info")
        if not isinstance(info, (list, tuple)) or len(info) < 3:
            return None

        try:
            content = str(info[1] or "").strip()
        except Exception:
            content = ""
        if not content:
            return None

        uid: int | None = None
        uname = ""
        user_info = info[2] if len(info) > 2 else None
        if isinstance(user_info, (list, tuple)) and len(user_info) >= 2:
            try:
                uid_val = int(user_info[0] or 0)
                uid = uid_val if uid_val > 0 else None
            except Exception:
                uid = None
            try:
                uname = str(user_info[1] or "").strip()
            except Exception:
                uname = ""

        if not uname:
            uname = str(event.get("uname") or event.get("user") or "").strip()

        return uid, uname, content

    def _coerce_event_data(self, event: dict[str, Any]) -> dict[str, Any] | None:
        raw = event.get("data")
        if isinstance(raw, dict):
            return raw

        if isinstance(raw, (list, tuple)):
            for item in raw:
                if isinstance(item, dict):
                    return item

        if hasattr(raw, "__dict__"):
            coerced = dict(vars(raw))
            inner = getattr(raw, "data", None)
            if isinstance(inner, dict):
                coerced.setdefault("data", inner)
            return coerced

    def _is_danmaku_event(self, event: dict[str, Any], cmd: str | None) -> bool:
        if isinstance(cmd, str) and cmd.startswith("DANMU_MSG"):
            return True

        data = event.get("data") if isinstance(event, dict) else None
        info = None
        if isinstance(data, dict):
            info = data.get("info")
        if info is None:
            info = event.get("info") if isinstance(event, dict) else None

        return isinstance(info, (list, tuple)) and len(info) >= 2

    def _is_gift_like_event(self, event: dict[str, Any]) -> bool:
        data = event.get("data") or {}
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            data = data.get("data")  # bilibili-api 的部分封装会套一层 data.data

        if isinstance(data, dict) and isinstance(data.get("data"), (list, tuple)):
            nested = data.get("data")
            if nested and isinstance(nested[0], dict):
                data = nested[0]

        if not isinstance(data, dict):
            return False

        gift_obj = data.get("gift") if isinstance(data.get("gift"), dict) else {}
        gift_name = (
            data.get("giftName")
            or data.get("gift_name")
            or gift_obj.get("giftName")
            or gift_obj.get("gift_name")
        )
        gift_id = (
            data.get("giftId")
            or data.get("gift_id")
            or gift_obj.get("giftId")
            or gift_obj.get("gift_id")
        )

        return bool(gift_name or gift_id)

    def _is_blind_box_trigger(self, content: str) -> bool:
        triggers = [t.strip().lower() for t in self.settings.blind_box_triggers if t.strip()]
        if not triggers:
            return False
        content_lower = content.strip().lower()
        return any(t and t in content_lower for t in triggers)

    def _format_currency(self, coins: int) -> str:
        try:
            # 金瓜子换算后的金额应为整数，去掉多余小数位以节省弹幕长度
            value = int(round(coins / 1000))
            return str(value)
        except Exception:
            return f"{coins / 1000:.2f}"

    def _render_template(self, template: str, **kwargs: object) -> str:
        try:
            return template.format(**kwargs)
        except Exception:
            return template

    def _default_blind_box_template(self) -> str:
        return "{uname} 心动盲盒投入¥{base_cost_yuan}，产出¥{reward_value_yuan}，盈亏{profit_sign}{profit_abs_yuan}"

    def _should_reply_blind_box(self, key: Any, ts: float) -> bool:
        cooldown_sec = 5
        last_ts = self._blind_box_cooldown.get(key)
        if last_ts is not None and ts - last_ts < cooldown_sec:
            return False
        self._blind_box_cooldown[key] = ts
        return True

    def _apply_gift_price(self, gift: GiftEvent) -> None:
        unit_price = None
        if gift.gift_id and gift.gift_id in self.settings.gift_price_by_id:
            unit_price = self.settings.gift_price_by_id[gift.gift_id]
        elif gift.gift_name and gift.gift_name in self.settings.gift_price_by_name:
            unit_price = self.settings.gift_price_by_name[gift.gift_name]

        if unit_price is None:
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug(
                    "未找到礼物单价，沿用原始金额 gift_id=%s gift_name=%s raw_total=%s",
                    gift.gift_id,
                    gift.gift_name,
                    gift.total_price,
                )
            return

        try:
            qty = max(int(gift.num), 1)
        except Exception:
            qty = 1

        computed = unit_price * qty
        if gift.total_price != computed:
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug(
                    "应用礼物价格缓存 gift_id=%s gift_name=%s 单价=%s 数量=%s 覆盖总价 %s -> %s",
                    gift.gift_id,
                    gift.gift_name,
                    unit_price,
                    qty,
                    gift.total_price,
                    computed,
                )
            gift.total_price = computed

    async def _handle_blind_box_query(self, event: dict[str, Any]) -> None:
        if not self.settings.blind_box_enabled:
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug("盲盒查询已关闭，忽略弹幕事件")
            return

        parsed = self._parse_danmaku_event(event)
        if parsed is None:
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug("盲盒查询解析弹幕失败 event_keys=%s", list(event.keys()))
            return
        uid, uname, content = parsed
        if not uname and uid is None:
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug("盲盒查询缺少用户信息 content=%s", content)
            return

        if not self._is_blind_box_trigger(content):
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug(
                    "弹幕未命中盲盒触发词 content=%s triggers=%s",
                    content,
                    self.settings.blind_box_triggers,
                )
            return

        ts = time.time()
        key = uid or f"guest:{uname}"
        if not self._should_reply_blind_box(key, ts):
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug("盲盒查询冷却中 uid=%s uname=%s", uid, uname)
            return

        try:
            base_total, reward_total = query_blind_box_totals(
                self.settings,
                uid=uid,
                uname=uname or None,
                base_gift=self.settings.blind_box_base_gift,
                reward_gifts=self.settings.blind_box_rewards,
            )
        except Exception:
            self.logger.exception("盲盒查询失败：读取礼物记录时出错")
            return
        profit = reward_total - base_total

        context = {
            "uname": uname or "神秘人",
            "uid": uid or "",
            "base_cost": base_total,
            "reward_value": reward_total,
            "profit": profit,
            "base_cost_yuan": self._format_currency(base_total),
            "reward_value_yuan": self._format_currency(reward_total),
            "profit_yuan": self._format_currency(profit),
            "profit_abs_yuan": self._format_currency(abs(profit)),
            "profit_sign": "+" if profit >= 0 else "-",
            "base_gift": self.settings.blind_box_base_gift,
        }

        template = (self.settings.blind_box_template or "").strip()
        if not template:
            template = self._default_blind_box_template()

        message = self._render_template(template, **context).strip()
        if not message:
            message = self._render_template(self._default_blind_box_template(), **context)

        self.logger.info(
            "盲盒查询：uid=%s uname=%s 触发词=%s 投入=%s 产出=%s 盈亏=%s",
            uid,
            context["uname"],
            content,
            base_total,
            reward_total,
            profit,
        )

        if self.settings.blind_box_send_danmaku and self.sender:
            try:
                await self.sender.send_custom_message(message)
            except Exception:
                self.logger.exception("发送盲盒盈亏弹幕失败")
        elif self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(
                "盲盒查询已计算但未发送弹幕 send_enabled=%s sender_present=%s",
                self.settings.blind_box_send_danmaku,
                bool(self.sender),
            )

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
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug(
                    "感谢节流：已达单日上限 uid=%s sent=%s limit=%s",
                    key,
                    daily_sent,
                    self.settings.thank_per_user_daily_limit,
                )
            return False

        decision = self.limiter.allow_with_reason(key, ts, ignore_cooldown=ignore_cooldown)
        if not decision.allowed:
            if self.logger.isEnabledFor(logging.DEBUG):
                retry_after = (
                    f"{decision.retry_after:.2f}s" if decision.retry_after is not None else "n/a"
                )
                self.logger.debug(
                    "感谢节流：跳过 uid=%s reason=%s retry_after=%s daily_count=%s",
                    key,
                    decision.reason,
                    retry_after,
                    decision.daily_count,
                )
            return False

        self._user_day_thanks[key] = daily_sent + 1
        return True

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
