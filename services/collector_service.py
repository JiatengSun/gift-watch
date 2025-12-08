from __future__ import annotations

from typing import Awaitable, Callable, Any, Dict
import logging

from bilibili_api import live

from config.settings import Settings

EventHandler = Callable[[Dict[str, Any]], Awaitable[None]]

class CollectorService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.room = live.LiveRoom(room_display_id=settings.room_id)
        # LiveDanmaku expects the numeric room display id, not a LiveRoom instance.
        # Passing the object results in query params containing the instance itself,
        # which raises "Invalid variable type" errors during connection.
        self.danmaku = live.LiveDanmaku(settings.room_id)
        self.logger = logging.getLogger(__name__)

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
        # 并在失败时回退到 ALL，避免礼物消息丢失或重复处理。
        if self._bind("SEND_GIFT", handler):
            return

        if self._bind("ALL", handler):
            return

        raise RuntimeError(
            "无法绑定 LiveDanmaku 事件处理器（SEND_GIFT 或 ALL），请检查 bilibili-api-python 版本的事件接口。"
        )

    async def run(self) -> None:
        await self.danmaku.connect()
