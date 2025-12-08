from __future__ import annotations

from typing import Awaitable, Callable, Any, Dict

from bilibili_api import live

from config.settings import Settings

EventHandler = Callable[[Dict[str, Any]], Awaitable[None]]

class CollectorService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.room = live.LiveRoom(room_display_id=settings.room_id)
        self.danmaku = live.LiveDanmaku(self.room)

    def bind_all_handler(self, handler: EventHandler) -> None:
        # bilibili-api 的事件系统在不同版本可能有细微差异
        # 主流用法是 @danmaku.on("ALL")
        try:
            @self.danmaku.on("ALL")
            async def _on_all(event):
                await handler(event)
        except Exception:
            # 兜底：如果装饰器不可用，尝试直接注册
            try:
                self.danmaku.add_event_listener("ALL", handler)  # type: ignore
            except Exception:
                raise RuntimeError("无法绑定 LiveDanmaku 事件处理器，请检查 bilibili-api-python 版本的事件接口。")

    async def run(self) -> None:
        await self.danmaku.connect()
