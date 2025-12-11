from __future__ import annotations

import asyncio
import logging
from typing import Optional

import aiohttp

from config.settings import Settings
from core.danmaku_sender import DanmakuSender


class AnnouncementService:
    """Periodically send danmaku to keep the room warm."""

    def __init__(self, settings: Settings, sender: DanmakuSender):
        self.settings = settings
        self.sender = sender
        self.logger = logging.getLogger(__name__)
        self._task: Optional[asyncio.Task] = None

    async def _is_live(self) -> bool:
        if not self.settings.announce_skip_offline:
            return True

        url = f"https://api.live.bilibili.com/room/v1/Room/room_init?id={self.settings.room_id}"
        timeout = aiohttp.ClientTimeout(total=5)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    resp.raise_for_status()
                    payload = await resp.json()
        except Exception as exc:
            self.logger.debug("定时弹幕检查直播状态失败", exc_info=exc)
            return False

        if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
            return False
        return payload["data"].get("live_status") == 1

    async def _loop(self) -> None:
        interval = max(self.settings.announce_interval_sec, 30)
        message = self.settings.announce_message.strip()
        if not message:
            self.logger.info("定时弹幕内容为空，跳过发送")
            return

        self.logger.info("定时弹幕已启用，间隔 %ss，开播时发送: %s", interval, message)

        while True:
            try:
                if await self._is_live():
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
