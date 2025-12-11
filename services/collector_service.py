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

    async def _fetch_room_init(self) -> Optional[Dict[str, Any]]:
        """Fetch room init info with asyncio + aiohttp to avoid urllib SSL errors on Windows."""

        try:
            import aiohttp
        except Exception as exc:  # pragma: no cover - 环境缺少 aiohttp 时回退
            self.logger.debug("aiohttp 不可用，跳过异步房间信息获取", exc_info=exc)
            return None

        url = f"https://api.live.bilibili.com/room/v1/Room/room_init?id={self.settings.room_id}"
        headers = {
            # B 站接口如果没有常见浏览器 UA 会返回 412，补充请求头提升成功率。
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/127.0.0.0 Safari/537.36"
            ),
            "Referer": "https://live.bilibili.com/",
        }
        timeout = aiohttp.ClientTimeout(total=5)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers) as resp:
                    resp.raise_for_status()
                    return await resp.json()
        except Exception as exc:
            self.logger.debug("获取房间信息失败", exc_info=exc)
            return None

    async def log_room_status(self) -> None:
        payload: Optional[Dict[str, Any]] = None

        # Primary path: aiohttp (handles TLS better on部分 Windows 环境)
        payload = await self._fetch_room_init()

        # Fallback to urllib in case aiohttp is unavailable at runtime
        if payload is None:
            url = f"https://api.live.bilibili.com/room/v1/Room/room_init?id={self.settings.room_id}"
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/127.0.0.0 Safari/537.36"
                ),
                "Referer": "https://live.bilibili.com/",
            }
            try:
                request = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(request, timeout=5) as resp:
                    payload_text = resp.read().decode("utf-8")
                payload = json.loads(payload_text)
            except Exception as exc:
                self.logger.debug("获取房间信息失败", exc_info=exc)

        if payload and payload.get("code") == 0 and isinstance(payload.get("data"), dict):
            info = payload["data"]
            self.logger.info(
                "房间初始化信息：room_id=%s uid=%s live_status=%s (1=直播中 0=未开播)",
                info.get("room_id"),
                info.get("uid"),
                info.get("live_status"),
            )
        elif payload is not None:
            self.logger.warning("无法获取房间信息：%s", payload)

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
        """
        优先按具体礼物事件进行绑定，确保连击事件不会漏算：

        1. 先尝试绑定 SEND_GIFT / COMBO_SEND，这样连击触发的 COMBO_SEND
           事件可以直接被处理，避免只结算第一个包裹的情况。
        2. 如果某些 bilibili-api 版本不存在这些事件或绑定方式抛错，则回退
           到 __ALL__，由上层自行解析 cmd，保证兼容性。
        3. 若所有方式均失败，抛出异常提示配置/版本问题。
        """
        bound = False
        for event_name in ("SEND_GIFT", "COMBO_SEND", "GUARD_BUY"):
            bound = self._bind(event_name, handler) or bound

        if bound:
            return

        if self._bind("__ALL__", handler):
            return

        raise RuntimeError(
            "无法绑定 LiveDanmaku 事件处理器（SEND_GIFT / COMBO_SEND 或 __ALL__），请检查 bilibili-api-python 版本的事件接口。"
        )

    async def run(self) -> None:
        await self.danmaku.connect()
