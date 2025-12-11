from __future__ import annotations

import asyncio
import logging
from typing import Optional

import aiohttp

from config.settings import Settings, get_settings
from core.danmaku_sender import DanmakuSender


class AnnouncementService:
    """Periodically send danmaku to keep the room warm."""

    def __init__(self, env_file: str | None, settings: Settings, sender: DanmakuSender):
        self.env_file = env_file
        self.settings = settings
        self.sender = sender
        self.logger = logging.getLogger(__name__)
        self._task: Optional[asyncio.Task] = None
        self._message_index: int = 0
        self._last_messages: list[str] | None = None

    async def _is_live(self, settings: Settings) -> bool:
        if not settings.announce_skip_offline:
            return True

        url = f"https://api.live.bilibili.com/room/v1/Room/room_init?id={settings.room_id}"
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
                    payload = await resp.json()
        except Exception as exc:
            self.logger.debug("定时弹幕检查直播状态失败", exc_info=exc)
            return False

        if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
            return False
        return payload["data"].get("live_status") == 1

    async def _loop(self) -> None:
        # Reload settings on every iteration so config changes apply without restart.
        while True:
            settings = get_settings(self.env_file)
            interval = max(settings.announce_interval_sec, 30)
            messages = [msg.strip() for msg in settings.announce_messages if msg.strip()]
            if messages != self._last_messages:
                self._message_index = 0
                self._last_messages = list(messages)

            if not settings.announce_enabled or not messages:
                self.logger.debug("定时弹幕未启用或内容为空，等待配置更新后再检查")
                await asyncio.sleep(interval)
                continue

            self.logger.debug("定时弹幕检查: 间隔 %ss，开播时发送=%s", interval, settings.announce_skip_offline)

            try:
                if await self._is_live(settings):
                    message = messages[self._message_index % len(messages)]
                    self._message_index = (self._message_index + 1) % len(messages)
                    await self.sender.send_custom_message(message)
                else:
                    self.logger.debug("房间未开播，跳过本轮定时弹幕")
            except Exception:
                self.logger.exception("发送定时弹幕失败")

            await asyncio.sleep(interval)

    def start(self) -> asyncio.Task:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())
        return self._task
