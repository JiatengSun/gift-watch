from __future__ import annotations

from typing import Awaitable, Callable, Any, Dict, Optional
import logging
import json
import urllib.request

from bilibili_api import live, Credential

from config.settings import Settings
from core.bili_client import get_bot_credential

EventHandler = Callable[[Dict[str, Any]], Awaitable[None]]

class CollectorService:
    def __init__(self, settings: Settings):
        self.settings = settings
        credential: Optional[Credential] = None
        if settings.bot_sessdata and settings.bot_bili_jct:
            credential = get_bot_credential(settings)

        self.room = live.LiveRoom(room_display_id=settings.room_id, credential=credential)
        # LiveDanmaku expects the numeric room display id, not a LiveRoom instance.
        # Passing the object results in query params containing the instance itself,
        # which raises "Invalid variable type" errors during connection.
        self.danmaku = live.LiveDanmaku(settings.room_id, credential=credential)
        self.logger = logging.getLogger(__name__)

    def log_room_status(self) -> None:
        url = f"https://api.live.bilibili.com/room/v1/Room/room_init?id={self.settings.room_id}"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                payload = resp.read().decode("utf-8")
            data = json.loads(payload)
            if data.get("code") == 0 and isinstance(data.get("data"), dict):
                info = data["data"]
                self.logger.info(
                    "房间初始化信息：room_id=%s uid=%s live_status=%s (1=直播中 0=未开播)",
                    info.get("room_id"),
                    info.get("uid"),
                    info.get("live_status"),
                )
            else:
                self.logger.warning("无法获取房间信息：%s", data)
        except Exception as exc:
            self.logger.debug("获取房间信息失败", exc_info=exc)

    def _bind(self, event_name: str, handler: EventHandler) -> bool:
        try:
            @self.danmaku.on(event_name)
            async def _wrapped(event):
                await handler(event)
            self.logger.info("已绑定事件监听：%s", event_name)
            return True
        except Exception:
            pass

        try:
            self.danmaku.add_event_listener(event_name, handler)  # type: ignore
            self.logger.info("已通过 add_event_listener 绑定事件：%s", event_name)
            return True
        except Exception as exc:
            self.logger.debug("事件监听绑定失败：%s", event_name, exc_info=exc)
            return False

    def bind_all_handler(self, handler: EventHandler) -> None:
        # 部分 bilibili-api 版本没有 "ALL" 事件，这里显式监听 SEND_GIFT，
        # 并在失败时回退到 __ALL__，避免礼物消息丢失或重复处理。
        if self._bind("SEND_GIFT", handler):
            return

        if self._bind("__ALL__", handler):
            return

        raise RuntimeError(
            "无法绑定 LiveDanmaku 事件处理器（SEND_GIFT 或 __ALL__），请检查 bilibili-api-python 版本的事件接口。"
        )

    async def run(self) -> None:
        await self.danmaku.connect()
