from __future__ import annotations

from typing import Mapping, Optional
import logging

from bilibili_api import live, Credential
from bilibili_api.exceptions import ResponseCodeException

class DanmakuSender:
    def __init__(
        self,
        room_id: int,
        credential: Credential,
        *,
        thank_message_single: str,
        thank_message_summary: str,
        thank_message_guard: str,
        max_length: int,
    ):
        self.room_id = room_id
        self.credential = credential
        self._room: Optional[live.LiveRoom] = None
        self._thank_message_single = thank_message_single
        self._thank_message_summary = thank_message_summary
        self._thank_message_guard = thank_message_guard
        self.max_length = max(0, max_length)
        self.logger = logging.getLogger(__name__)

    def _get_room(self) -> live.LiveRoom:
        if self._room is None:
            # 使用 display_id 更友好
            self._room = live.LiveRoom(room_display_id=self.room_id, credential=self.credential)
        return self._room

    def _render(self, template: str, **kwargs: object) -> str:
        try:
            return template.format(**kwargs)
        except Exception:
            return template

    def _trim(self, message: str) -> tuple[str, bool]:
        if self.max_length and len(message) > self.max_length:
            return message[: self.max_length], True
        return message, False

    async def _send(self, message: str) -> None:
        if not message:
            return
        trimmed, _ = self._trim(message.strip())
        if not trimmed:
            return

        room = self._get_room()
        try:
            await room.send_danmaku(live.Danmaku(trimmed))
        except ResponseCodeException as exc:
            if exc.code == 1003212:
                fallback_limit = max(1, (self.max_length or len(trimmed)) - 1)
                fallback = trimmed[:fallback_limit]
                if len(fallback) < len(trimmed):
                    self.logger.warning(
                        "弹幕超长已截断 length=%s->%s content=%s", len(message), len(fallback), trimmed
                    )
                    await room.send_danmaku(live.Danmaku(fallback))
                    return
            raise

    async def send_thanks(self, uname: str, gift_name: str, num: int = 1) -> None:
        msg = self._render(self._thank_message_single, uname=uname, gift_name=gift_name, num=num)
        await self._send(msg)

    async def send_guard_thanks(self, uname: str, guard_name: str) -> None:
        msg = self._render(self._thank_message_guard, uname=uname, guard_name=guard_name)
        await self._send(msg)

    async def send_summary_thanks(self, uname: str, gifts: Mapping[str, int]) -> None:
        parts = [f"{name} x{count}" for name, count in gifts.items()]
        gift_text = "，".join(parts) if parts else "礼物"
        msg = self._render(self._thank_message_summary, uname=uname, gifts=gift_text)
        await self._send(msg)

    async def send_custom_message(self, message: str) -> None:
        await self._send(message)

    def reconfigure(
        self,
        *,
        room_id: int | None = None,
        credential: Credential | None = None,
        thank_message_single: str | None = None,
        thank_message_summary: str | None = None,
        thank_message_guard: str | None = None,
        max_length: int | None = None,
    ) -> None:
        if room_id is not None and room_id != self.room_id:
            self.room_id = room_id
            self._room = None
        if credential is not None and credential is not self.credential:
            self.credential = credential
            self._room = None
        if thank_message_single is not None:
            self._thank_message_single = thank_message_single
        if thank_message_summary is not None:
            self._thank_message_summary = thank_message_summary
        if thank_message_guard is not None:
            self._thank_message_guard = thank_message_guard
        if max_length is not None:
            self.max_length = max(0, max_length)
